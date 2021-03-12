import docker
import logging
from logging.handlers import RotatingFileHandler
import datetime
import json
import time
import yaml
import sys
import requests
import pathlib
import os


CLIENT = docker.from_env()
RCLONE_USER = "user"
RCLONE_PASS = "pass"
rclone_container = CLIENT.containers.get("rclone")


class LogSetup:
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%d-%m-%Y %H:%M:%S"
    )
    parent_directory = pathlib.Path(__file__).parent
    log_file = pathlib.Path(parent_directory, "rclone_sync.log")

    @classmethod
    def get_console_handler(self):
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(self.formatter)
        return console_handler

    @classmethod
    def get_file_handler(self):
        file_handler = RotatingFileHandler(
            self.log_file, maxBytes=1000000, backupCount=0
        )
        file_handler.setFormatter(self.formatter)
        return file_handler

    @classmethod
    def get_logger(self, logger_name):
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG)
        logger.addHandler(self.get_console_handler())
        logger.addHandler(self.get_file_handler())
        logger.propagate = False
        return logger


logger = LogSetup.get_logger("rclone")


class PushoverNotifications:
    def __init__(self, user_token, app_token):
        self.url = "https://api.pushover.net/1/messages.json"
        self.user_token = user_token
        self.app_token = app_token

    def send_notification(self, title, message):
        data = {
            "user": self.user_token,
            "token": self.app_token,
            "title": title,
            "message": message,
        }
        response = requests.post(self.url, data=data)
        logger.info(
            "Recieved response code: %s from %s", response.status_code, self.url
        )
        return response.status_code


class JobResult:
    def __init__(self, job_name, job_successful, job_error, job_timed_out):
        self.job_name = job_name
        self.job_successful = job_successful
        self.job_error = job_error
        self.job_timed_out = job_timed_out

    def __repr__(self):
        return self.job_name


def stop_containers(containers_to_stop=None):
    logger.info("Stopping containers: %s", containers_to_stop)
    running_containers = CLIENT.containers.list()
    stopped_containers = []
    if not containers_to_stop:
        return stopped_containers
    for container in running_containers:
        if container.name in containers_to_stop:
            logger.info("Stopping container: %s", container.name)
            container.stop()
            stopped_containers.append(container.name)
    return stopped_containers


def start_containers(containers_to_start):
    logger.info("Starting containers: %s", containers_to_start)
    if containers_to_start:
        for container_name in containers_to_start:
            container = CLIENT.containers.get(container_name)
            logger.info("Starting container: %s", container_name)
            container.start()


def get_rclone_options():
    command = (
        f"rclone rc options/get --rc-user={RCLONE_USER} --rc-pass={RCLONE_PASS}"
    )
    result = rclone_container.exec_run(command)
    options = json.loads(result.output.decode())
    return options


def set_rclone_options(destination_remote, destination_folder, transfers=1):
    """
    Set options for rc instance.

    :param str destination_folder: Target folder in root of remote.
    :param int transfers: Max number of simultaneous transfers.
    :param int max_duration: Max job runtime in NS.
    :return:
    """
    now = datetime.datetime.now()
    date_time = now.strftime("%d_%m_%Y")
    options = json.dumps(
        {
            "main": {
                "BackupDir": f"{destination_remote}:archive/{destination_folder}/{destination_folder}_{date_time}",
                "Transfers": transfers,
            }
        }
    )
    command = (
        f"rclone rc options/set --json '{options}' "
        f"--rc-user={RCLONE_USER} --rc-pass={RCLONE_PASS}"
    )
    logger.debug(command)
    return rclone_container.exec_run(command)


def rclone_sync(source_directory, destination_remote, destination_folder):
    command_json = json.dumps(
        {
            "srcFs": source_directory,
            "dstFs": destination_remote + ":" + destination_folder,
            "_async": True,
        }
    )
    command = f"rclone rc sync/sync --json '{command_json}' --rc-user={RCLONE_USER} --rc-pass={RCLONE_PASS}"
    logger.debug(command)
    return rclone_container.exec_run(command)


def get_job_status(job_id):
    command_json = '{"jobid": %s}' % job_id
    command = (
        f"rclone rc --json '{command_json}' job/status "
        f"--rc-user={RCLONE_USER} --rc-pass={RCLONE_PASS}"
    )
    output = json.loads(rclone_container.exec_run(command).output.decode())
    return output


def cancel_rclone_job(job_id):
    command_json = '{"jobid": %s}' % job_id
    command = (
        f"rclone rc --json '{command_json}' job/stop "
        f"--rc-user={RCLONE_USER} --rc-pass={RCLONE_PASS}"
    )
    output = json.loads(rclone_container.exec_run(command).output.decode())
    return output.get("finished")


def poll_for_completion(job_id, stopped_containers, timeout=None):
    timeout_start = time.time()
    job_output = {}
    timed_out = False
    while not job_output.get("finished"):
        logger.debug("Job %s not done, checking again soon...", job_id)
        time.sleep(10)
        job_output = get_job_status(job_id)
        if timeout is not None:
            if time.time() > timeout_start + timeout:
                logger.info(f"Job %s has timed out, cancelling...", job_id)
                cancel_rclone_job(job_id)
                timed_out = True
                break
    else:
        logger.info("Job done! Spinning up containers...")
    start_containers(stopped_containers)
    return (job_output["success"], job_output["error"], timed_out)


def directory_is_empty(source_directory):
    is_empty = False
    if os.path.exists(source_directory) and os.path.isdir(source_directory):
        if not os.listdir(source_directory):
            is_empty = True
    return is_empty


def run_job(
    source_directory,
    destination_remote,
    destination_directory,
    transfers=1,
    timeout=None,
    containers_to_stop=None,
):
    logger.info(
        f"Starting job, src: %s, dest: %s:%s, timeout: %s",
        source_directory,
        destination_remote,
        destination_directory,
        timeout,
    )
    # Todo: Enable this when I figure out how to check directories on the
    #  container, not the host
    # if directory_is_empty(source_directory):
    #     logger.warning(
    #         "Source directory %s is empty, skipping sync", source_directory
    #     )
    #     return False, "Source directory empty", False
    initial_transfers = get_rclone_options()["main"]["Transfers"]
    stopped_containers = stop_containers(containers_to_stop)
    set_rclone_options(
        destination_remote,
        destination_directory,
        transfers=transfers,
    )
    sync_result = rclone_sync(
        source_directory, destination_remote, destination_directory
    )
    job_id = json.loads(sync_result.output.decode()).get("jobid")
    logger.info("Running job: %s", job_id)
    job_successful, job_error, job_timed_out = poll_for_completion(
        job_id, stopped_containers, timeout
    )
    set_rclone_options(
        destination_remote, destination_directory, transfers=initial_transfers
    )
    return (job_successful, job_error, job_timed_out)


def calculate_time_until_cutoff():
    now = datetime.datetime.now()
    cutoff_hour = 9
    cutoff_time = datetime.datetime(now.year, now.month, now.day, cutoff_hour)
    time_delta = cutoff_time - now
    return time_delta


def read_yaml(jobs_yml_filename):
    with open(jobs_yml_filename) as file:
        return yaml.load(file, Loader=yaml.FullLoader)


def sync_remotes(remote_1, remote_2):
    options = json.dumps(
        {
            "main": {
                "BackupDir": "",
                "Transfers": 20,
            }
        }
    )
    command = (
        f"rclone rc options/set --json '{options}' "
        f"--rc-user={RCLONE_USER} --rc-pass={RCLONE_PASS}"
    )
    logger.debug(command)
    rclone_container.exec_run(command)
    command_json = json.dumps(
        {
            "srcFs": remote_1 + ":",
            "dstFs": remote_2 + ":",
            "_async": True,
        }
    )
    command = f"rclone rc sync/sync --json '{command_json}' --rc-user={RCLONE_USER} --rc-pass={RCLONE_PASS}"
    logger.debug(command)
    sync_result = rclone_container.exec_run(command)
    job_id = json.loads(sync_result.output.decode()).get("jobid")
    logger.info("Running job: %s", job_id)
    return poll_for_completion(job_id, None)


def notify_results(notifier: PushoverNotifications, job_results):
    title = "Rclone"
    successful_jobs = []
    timed_out_jobs = []
    failed_jobs = []
    for index, job_result in enumerate(job_results):
        if job_result.job_successful:
            successful_jobs.append(job_result)
        elif job_result.job_timed_out:
            timed_out_jobs.append(job_result)
        elif job_result.job_error:
            failed_jobs.append(job_result)

    msg = f"{len(successful_jobs)} jobs completed successfully"
    if len(timed_out_jobs) > 0:
        msg += f", {len(timed_out_jobs)} timed out"
    if len(failed_jobs) > 0:
        msg += f", {len(failed_jobs)} failed"
    msg += "!"

    # List failed jobs if we have any
    if len(failed_jobs) > 0:
        msg += "\n\nFailed jobs:"
    for job in failed_jobs:
        msg += "\n* " + job.job_name

    # List timed out jobs if we have any
    if len(timed_out_jobs) > 0:
        msg += "\n\nTimed out jobs:"
    for job in timed_out_jobs:
        msg += "\n* " + job.job_name

    logger.info(msg)
    notifier.send_notification(title, msg)


def main():
    config = read_yaml("/home/pi/Docker/rclone/jobs.yml")
    if config.get("pushover"):
        notifier = PushoverNotifications(
            config["pushover"]["user_token"], config["pushover"]["app_token"]
        )
    job_results = []
    for job_name, job_inputs in config["jobs"].items():
        seconds_until_cutoff = calculate_time_until_cutoff().seconds
        job_successful, job_error, job_timed_out = run_job(
            job_inputs.get("source_directory"),
            job_inputs.get("destination_remote"),
            job_inputs.get("destination_directory"),
            transfers=job_inputs.get("transfers"),
            timeout=seconds_until_cutoff,
            containers_to_stop=job_inputs.get("containers_to_stop"),
        )
        job_results.append(
            JobResult(job_name, job_successful, job_error, job_timed_out)
        )
        if job_timed_out:
            break
    sync_result = sync_remotes("gdrive_1", "gdrive_2")
    job_results.append(JobResult("sync_remotes", *sync_result))
    notify_results(notifier, job_results)
    logger.info("DONE")


if __name__ == "__main__":
    main()
