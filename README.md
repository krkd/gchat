Gevent Chat
===========

To start server setup vagrant vm
> vagrant up

then execute ssh to vm
> vagrant ssh

and lunch application
> cd /vagrant && uwsgi config.ini

after that application will serve requests on 8000 port
connect with ws protocol to route '/ '
