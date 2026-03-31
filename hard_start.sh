docker rm $(docker ps -a -q) -f
docker rmi $(docker images -a -q) -f
docker system prune -a -f
git pull
python3 scripts/sync-portainer-password-from-env.py
docker compose up -d --build
