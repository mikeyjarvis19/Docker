import docker
import logging
import datetime
import json
import time

CLIENT = docker.from_env()
RCLONE_USER = "user"
RCLONE_PASS = "pass"


def stop_containers(containers_to_stop=None):
    logging.info("Stopping containers: %s", containers_to_stop)
    running_containers = CLIENT.containers.list()
    stopped_containers = []
    if not containers_to_stop:
        return stopped_containers
    for container in running_containers:
        if container.name in containers_to_stop:
            logging.info("Stopping container: %s", container.name)
            print("Stopping container:", container.name)
            container.stop()
            stopped_containers.append(container.name)
    return stopped_containers


def start_containers(containers_to_start):
    logging.info("Starting containers: %s", containers_to_start)
    for container_name in containers_to_start:
        container = CLIENT.containers.get(container_name)
        logging.info("Starting container: %s", container_name)
        print("Starting container:", container_name)
        container.start()


def get_rclone_options():
    rclone_container = CLIENT.containers.get("rclone")
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
    rclone_container = CLIENT.containers.get("rclone")
    command = (
        f"rclone rc options/set --json '{options}' "
        f"--rc-user={RCLONE_USER} --rc-pass={RCLONE_PASS}"
    )
    print(command)
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
    print(command)
    rclone_container = CLIENT.containers.get("rclone")
    return rclone_container.exec_run(command)


def rclone_job_completed(job_id):
    command_json = '{"jobid": %s}' % job_id
    command = (
        f"rclone rc --json '{command_json}' job/status "
        f"--rc-user={RCLONE_USER} --rc-pass={RCLONE_PASS}"
    )
    rclone_container = CLIENT.containers.get("rclone")
    output = json.loads(rclone_container.exec_run(command).output.decode())
    return output.get("finished")


def cancel_rclone_job(job_id):
    command_json = '{"jobid": %s}' % job_id
    command = (
        f"rclone rc --json '{command_json}' job/stop "
        f"--rc-user={RCLONE_USER} --rc-pass={RCLONE_PASS}"
    )
    rclone_container = CLIENT.containers.get("rclone")
    output = json.loads(rclone_container.exec_run(command).output.decode())
    return output.get("finished")


def poll_for_completion(job_id, stopped_containers, timeout=None):
    timeout_start = time.time()
    while not rclone_job_completed(job_id):
        print(f"Job {job_id} not done, checking again soon...")
        time.sleep(10)
        if timeout is not None:
            if time.time() > timeout_start + timeout:
                print(f"Job {job_id} has timed out, cancelling...")
                cancel_rclone_job(job_id)
                break
    else:
        print("Job done! Spinning up containers...")
    start_containers(stopped_containers)


def run_job(
    source_directory,
    destination_remote,
    destination_directory,
    transfers=1,
    timeout=None,
    containers_to_stop=None,
):
    print(
        f"Starting job, src: {source_directory}, dest: {destination_remote}:{destination_directory}, timeout: {timeout}"
    )
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
    print(f"Running job: {job_id}")
    poll_for_completion(job_id, stopped_containers, timeout)
    set_rclone_options(
        destination_remote, destination_directory, transfers=initial_transfers
    )


def calculate_time_until_cutoff():
    now = datetime.datetime.now()
    cutoff_hour = 9
    cutoff_time = datetime.datetime(now.year, now.month, now.day, cutoff_hour)
    time_delta = cutoff_time - now
    return time_delta


def main():
    container_names = [
        "sonarr",
        "radarr",
        "tautulli",
        "openvpn-transmission_transmission_1",
    ]
    run_job(
        "/data/synced",
        "encrypted_gdrive_1",
        "home_synced",
        transfers=4,
        containers_to_stop=container_names,
    )
    seconds_until_cutoff = calculate_time_until_cutoff().seconds
    run_job(
        "/data/hdd/videos",
        "encrypted_gdrive_1",
        "hdd_videos",
        transfers=1,
        timeout=seconds_until_cutoff,
    )

    print("DONE")


if __name__ == "__main__":
    main()
