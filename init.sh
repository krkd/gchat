apt-get update
apt-get install -y python-dev python-pip libssl-dev redis-server
pip install gevent redis https://github.com/unbit/uwsgi/archive/master.zip
