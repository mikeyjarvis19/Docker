import docker
import logging
import datetime
import json
import time

CLIENT = docker.from_env()
RCLONE_USER = "user"
RCLONE_PASS = "pass"


def stop_containers():
    containers_to_stop = [
        "sonarr",
        "radarr",
        "tautulli",
        "openvpn-transmission_transmission_1",
    ]
    logging.info("Stopping containers: %s", containers_to_stop)
    running_containers = CLIENT.containers.list()
    stopped_containers = []
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
    command = f"rclone rc options/get --rc-user={RCLONE_USER} --rc-pass={RCLONE_PASS}"
    result = rclone_container.exec_run(command)
    options = json.loads(result.output.decode())
    return options


def set_rclone_options(target_folder, transfers=1, max_duration=0):
    """
    Set options for rc instance.
    :param str target_folder: Target folder in root of remote.
    :param int transfers: Max number of simultaneous transfers.
    :param int max_duration: Max job runtime in NS.
    :return:
    """
    now = datetime.datetime.now()
    date_time = now.strftime("%d_%m_%Y")
    options = json.dumps(
        {
            "main": {
                "BackupDir": f"encrypted_gdrive_1:archive/{target_folder}/{target_folder}_{date_time}",
                "MaxDuration": max_duration,
                "Transfers": transfers,
            }
        }
    )
    rclone_container = CLIENT.containers.get("rclone")
    command = (
        f"rclone rc options/set --json '{options}' "
        f"--rc-user={RCLONE_USER} --rc-pass={RCLONE_PASS}"
    )
    return rclone_container.exec_run(command)


def rclone_sync():
    command_json = '{"srcFs": "/data/synced", "dstFs": "encrypted_gdrive_1:home_synced", "_async": true}'
    command = f"rclone rc sync/sync --json '{command_json}' --rc-user={RCLONE_USER} --rc-pass={RCLONE_PASS}"
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


def poll_for_completion(job_id, stopped_containers):
    while not rclone_job_completed(job_id):
        print(f"Job {job_id} not done, checking again soon...")
        time.sleep(5)
    print("Job done! Spinning up containers...")
    start_containers(stopped_containers)


def main():
    print(get_rclone_options())
    stopped_containers = stop_containers()
    print("SETTING RCLONE OPTIONS")
    set_rclone_options("home_synced")
    print(get_rclone_options())
    sync_result = rclone_sync()
    job_id = json.loads(sync_result.output.decode()).get("jobid")
    poll_for_completion(job_id, stopped_containers)


if __name__ == "__main__":
    main()
