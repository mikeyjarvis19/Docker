import docker
import logging
import datetime
import json

CLIENT = docker.from_env()
RCLONE_USER = "user"
RCLONE_PASS = "pass"


def stop_containers():
    containers_to_stop = ["sonarr", "radarr", "tautulli"]
    logging.info("Stopping containers: %s", containers_to_stop)
    running_containers = CLIENT.containers.list()
    stopped_containers = []
    for container in running_containers:
        if container.name in containers_to_stop:
            logging.info("Stopping container: %s", container)
            container.stop()
            stopped_containers.append(container.name)
    return stopped_containers


def start_containers(containers_to_start):
    logging.info("Starting containers: %s", containers_to_start)
    for container_name in containers_to_start:
        container = CLIENT.containers.get(container_name)
        logging.info("Starting container: %s", container_name)
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
    pass


def main():
    # stopped_containers = stop_containers()
    rclone_options = get_rclone_options()
    set_rclone_options("home_synced")
    # start_containers(stopped_containers)


if __name__ == "__main__":
    main()
