# See https://stackoverflow.com/a/48470187/7752249
rc_pass="mypass"
json_fmt='{"main": {"BackupDir": "encrypted_gdrive_1:archive/home_synced/home_synced_%s"}}'
json_str=$(printf "$json_fmt" "$(date +%d_%m_%Y)")
docker exec rclone rclone rc options/set --json "$json_str" --rc-user=$rc_user --rc-pass=$rc_pass
#options=$(docker exec rclone rclone rc options/get --rc-user=$rc_user --rc-pass=$rc_pass)
#echo $options
docker exec rclone rclone rc sync/sync srcFs="/data/synced" dstFs=encrypted_gdrive_1:home_synced --rc-user=$rc_user --rc-pass=$rc_pass -async
docker exec -d rclone rclone rc options/set --json '{"main": {"BackupDir": ""}}' --rc-user=$rc_user --rc-pass=$rc_pass
