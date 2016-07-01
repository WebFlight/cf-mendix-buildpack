from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
import cgi
import json
import subprocess
import time
import os
from m2ee import logger
import urllib2
import traceback
from base64 import b64encode
from start import get_admin_port

ROOT_DIR = os.getcwd() + '/'
MXBUILD_FOLDER = ROOT_DIR + 'mxbuild/'


project_dir = '.local/project'
deployment_dir = os.path.join(project_dir, 'deployment')

for dir in (MXBUILD_FOLDER, project_dir, deployment_dir):
    subprocess.call(('mkdir', '-p', dir))
mpk_file = os.path.join(project_dir, 'app.mpk')


def get_mpr_file(project_dir):
    for filename in os.listdir(project_dir):
        if filename.endswith('.mpr'):
            return os.path.join(project_dir, filename)
    raise Exception('could not get runtime_version')


def detect_runtime_version():
    with open("model/metadata.json") as f:
        metadata = json.load(f)
    return metadata['RuntimeVersion']


runtime_version = detect_runtime_version()


class StoreHandler(BaseHTTPRequestHandler):

    def do_POST(self):
        try:
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    'REQUEST_METHOD': 'POST',
                    'CONTENT_TYPE': self.headers['Content-Type'],
                })
            if 'file' in form:
                data = form['file'].file.read()
                open(mpk_file, "wb").write(data)
                mxbuild_response = build(mpk_file, ticker())
                if 'restartRequired' in str(mxbuild_response):
                    logger.info(str(mxbuild_response))
                    logger.info("Restarting app")
                    self.server.mxbuild_restart_callback()
                else:
                    logger.info(str(mxbuild_response))
                    logger.info("Reloading model")
                    reload_model()
                return self._terminate(200, {'state': 'STARTED'}, mxbuild_response)
            else:
                return self._terminate(401, {'state': 'FAILED', 'errordetails': 'No MPK found'})
        except Exception as e:
            details = traceback.format_exc()
            return self._terminate(500, {'state': 'FAILED', 'errordetails': details})

    def _terminate(self, status_code, data, mxbuild_response=None):
        if mxbuild_response:
            mxbuild_json = json.loads(mxbuild_response.read())
            data['buildstatus'] = json.dumps(mxbuild_json['problems'])
        self.send_response(status_code)
        self.send_header('Content-type','application/json')
        self.end_headers()
        data['code'] = status_code
        self.wfile.write(json.dumps(data))


def ensure_mxbuild_version(version):
    print 'ensuring mxbuild'
    if os.path.isdir(MXBUILD_FOLDER + version):
        return
    else:
        default_mxbuild_url = 'https://cdn.mendix.com/runtime/mxbuild-%s.tar.gz' % version
        mxbuild_url = os.environ.get('FORCED_MXBUILD_URL', default_mxbuild_url)
        subprocess.check_call((
            'wget',
            '-q',
            mxbuild_url,
            '-O', MXBUILD_FOLDER + version + '.tar.gz',
        ))
        subprocess.check_call(('mkdir', '-p', MXBUILD_FOLDER + version))
        subprocess.check_call((
            'tar',
            'xzf',
            MXBUILD_FOLDER + version + '.tar.gz',
            '-C', MXBUILD_FOLDER + version,
        ))
        subprocess.call(('rm', MXBUILD_FOLDER + version + '.tar.gz'))


def apply_changes():
    for name in ('web', 'model'):
        subprocess.call(('cp -r ' + os.path.join(deployment_dir, name, "*") + ' ' + os.path.join(ROOT_DIR, name)), shell=True)
        subprocess.call(('rm -R ' + os.path.join(deployment_dir, name, "*")), shell=True)


def ensure_mono():
    if os.path.isdir(ROOT_DIR + 'mono'):
        return
    else:
        subprocess.check_call((
            'wget',
            '-q',
            'http://cdn.mendix.com/mx-buildpack/mono-3.10.0.tar.gz',
            '-O', ROOT_DIR + 'mono.tar.gz'
        ))
        subprocess.check_call((
            'tar',
            'xzf',
            ROOT_DIR + 'mono.tar.gz',
            '-C', ROOT_DIR
        ))
        subprocess.call(('rm', ROOT_DIR + 'mono.tar.gz'))


def runmxbuild(project_dir, runtime_version):
    before = time.time()
    body = {'args': ['--target=pages', '--loose-version-check', get_mpr_file(project_dir)]}
    headers = {
        'Content-Type': 'application/json',
    }

    body = json.dumps(body)
    req = urllib2.Request(
        url='http://localhost:6666/',
        data=body,
        headers=headers,
    )
    response = urllib2.urlopen(req, timeout=10)
    if (response.getcode() != 200):
        raise Exception('http error' + str(response.getcode()))
    print 'MxBuild compilation succeeded'
    print 'MxBuild took', time.time() - before, 'seconds'
    return response


def build(mpk_file, ticker):
    subprocess.check_call(('unzip', '-oqq', mpk_file, '-d', project_dir))
    print 'unzip', ticker.next()
    print 'runtime_version', ticker.next()
    response = runmxbuild(project_dir, runtime_version)
    print 'mxbuild', ticker.next()
    apply_changes()
    print 'apply new changes', ticker.next()
    return response


def reload_model():
    PASSWORD = os.environ.get('ADMIN_PASSWORD')
    headers = {
        'Content-Type': 'application/json',
        'X-M2EE-Authentication': b64encode(PASSWORD),
        'Authorization': 'Basic ' + b64encode('MxAdmin:' + PASSWORD),
    }

    body = {"action": "reload_model"}
    body = json.dumps(body)
    req = urllib2.Request(
        url='http://localhost:' + str(get_admin_port()) + '/',
        data=body,
        headers=headers,
    )
    response = urllib2.urlopen(req, timeout=5)
    response_headers = response.info()
    parsed_response = json.load(response)
    if response.getcode() != 200:
        raise Exception('http error' + str(response.getcode()))
    print 'RELOADED MODEL GREAT SUCCESS!!'


def ticker():
    prev = time.time()
    while True:
        last = time.time()
        yield last - prev
        prev = last


def start_mxbuild_server():
    env = dict(os.environ)
    env['LD_LIBRARY_PATH'] = os.path.join('lib', 'mono-lib')
    subprocess.check_call([
        'sed',
        '-i',
        's|/app/vendor/mono/lib/libgdiplus.so|%s|g' % os.path.join(
            'lib', 'mono-lib', 'libgdiplus.so'
        ),
        os.path.join('mono', 'etc', 'mono', 'config'),
    ])
    subprocess.check_call([
        'sed',
        '-i',
        's|/usr/lib/libMonoPosixHelper.so|%s|g' % os.path.join(
            'lib', 'mono-lib', 'libMonoPosixHelper.so'
        ),
        os.path.join('mono', 'etc', 'mono', 'config'),
    ])
    subprocess.Popen([
        'mono/bin/mono',
        '--config', 'mono/etc/mono/config',
        'mxbuild/%s/modeler/mxbuild.exe' % runtime_version,
        '--serve',
        '--port=6666'], env=env)


def do_run(port, restart_callback):
    ensure_mono()
    ensure_mxbuild_version(runtime_version)
    print('Going to listen on port ', port)
    server = HTTPServer(('', port), StoreHandler)
    server.mxbuild_restart_callback = restart_callback
    start_mxbuild_server()
    server.serve_forever()