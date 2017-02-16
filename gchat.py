
import uwsgi
import gevent.select
import redis
import json
from datetime import datetime
from gevent.queue import Queue

PUBSUB_KEY = 'room1'


def get_storage_key(room):
    return '{}:data'.format(room)


class Broadcaster(object):
    connections = set()

    @classmethod
    def add(cls, connection):
        cls.connections.add(connection)

    @classmethod
    def remove(cls, connection):
        pass
        # cls.connections.remove(connection)

    @classmethod
    def count(cls):
        return len(cls.connections)

    @classmethod
    def broadcast(cls, msg):
        def do_broadcast():
            for c in cls.connections:
                c.send(msg)

        gevent.spawn(do_broadcast)


class Listner(object):
    def __init__(self, redis):
        self.greenlet = None
        self.channel = None
        self.redis = redis
        self.running = False

    def _exit(self):
        self.greenlet.unlink(self._exit)
        gevent.kill(self.greenlet)

    def start(self):
        if self.running:
            return
        self.running = True

        self.channel = self.redis.pubsub()
        self.channel.subscribe(PUBSUB_KEY)

        self.greenlet = gevent.spawn(self.subscribe)
        self.greenlet.link(self._exit)

    def subscribe(self):
        for msg in self.channel.listen():
            if not msg:
                continue

            if msg['type'] == 'message':
                Broadcaster.broadcast(msg['data'])

            # TODO: handle disconnect and unsubsribe


class Connection(object):
    def __init__(self, redis, core_id):
        self.ctx = None
        self.send_queue = Queue()
        self.jobs = []
        self.redis = redis
        self.user_id = core_id

    def _recv_job(self):
        while True:
            try:
                payload = uwsgi.websocket_recv(request_context=self.ctx)
            except IOError:
                # connection was terminated
                self._exit()
            else:
                self.on_message(payload)

    def _send_job(self):
        while True:
            payload = self.send_queue.get()
            uwsgi.websocket_send(payload, request_context=self.ctx)

    def _exit(self, *args):
        for j in self.jobs:
            j.unlink(self._exit)

        gevent.killall(self.jobs)
        Broadcaster.remove(self)
        self.on_exit()

    def on_message(self, data):
        now = datetime.now()
        with self.redis.pipeline(transaction=False) as pipe:
            pipe.rpush(
                get_storage_key(PUBSUB_KEY),
                json.dumps({
                    'user_id': self.user_id,
                    'datetime': str(now),
                    'message': data
                })
            )
            pipe.publish(PUBSUB_KEY, data)
            pipe.execute()

    def on_exit(self):
        pass

    def on_open(self):
        data = self.redis.lrange(get_storage_key(PUBSUB_KEY), 0, -1)
        if not data:
            return

        for payload in data:
            self.send(payload)

    def send(self, data):
        self.send_queue.put(data)

    def start(self, ctx):
        self.ctx = ctx

        Broadcaster.add(self)

        self.on_open()

        self.jobs.extend([
            gevent.spawn(self._recv_job),
            gevent.spawn(self._send_job),
        ])

        for j in self.jobs:
            j.link(self._exit)

        gevent.joinall(self.jobs)

redis = redis.StrictRedis(
    host=uwsgi.opt['redis.host'],
    port=uwsgi.opt['redis.port'],
    db=uwsgi.opt['redis.db']
)
listner = Listner(redis)


def application(environ, start_response):
    listner.start()
    if environ['PATH_INFO'] != '/':
        start_response('404 Not Found', [('Content-Type', 'text/html')])
        return [b'<p>Page Not Found</p>\n']

    uwsgi.websocket_handshake()
    connection = Connection(redis, environ['uwsgi.core'])
    connection.start(uwsgi.request_context())
    return ''
