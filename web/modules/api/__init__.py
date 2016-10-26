import errno
import io
import json
import os
import sys
from datetime import datetime
from hashlib import md5
from urlparse import urlparse

from PIL import Image
from sqlalchemy import desc
from tornado import web

from ext.blueprint import Blueprint, RequestHandler
from ext.tools import Command
from web import database
from web.models.models import MementoModel


class API(Blueprint):
    def __init__(self, *args, **settings):
        Blueprint.__init__(self, url_prefix='/api', *args, **settings)

        self.cache_dir = self.application.settings.get('cache_dir')
        self.screenshot_dir = os.path.join(
            self.application.settings.get('cache_dir'), 'screenshot')
        self.log_dir = os.path.join(
            self.application.settings.get('cache_dir'), 'log')
        self.html_dir = os.path.join(
            self.application.settings.get('cache_dir'), 'html')

        try:
            os.makedirs(self.screenshot_dir)
            os.makedirs(self.log_dir)
            os.makedirs(self.html_dir)
        except OSError, e:
            if e.errno != errno.EEXIST:
                raise


    '''
    Handlers =================================================================
    '''
    class Index(RequestHandler):
        route = ['', '/']

        @web.asynchronous
        def get(self, *args, **kwargs):
            referer = self.request.headers.get("Referer")
            parsed_uri = urlparse(referer)
            domain = '{uri.scheme}://{uri.netloc}/'.format(uri=parsed_uri)

            self.render('.index.html', domain=domain)

    class ProgressCheckDamage(RequestHandler):
        route = ['/damage/progress/([^/]+)',
                 '/damage/progress/([^/]+)/([^/]+)']

        @web.asynchronous
        def get(self, uri, start=0):
            start = int(start)
            hashed_uri = md5(uri).hexdigest()

            crawler_log_file = '{}.crawl.log'.format(os.path.join(
                self.blueprint.log_dir, hashed_uri))

            with open(crawler_log_file, 'rb') as f:
                for idx, line in enumerate(f.readlines()):
                    if idx >= start:
                        self.write(line)
                self.finish()

    class CheckError(RequestHandler):
        route = ['/damage/error/([^/]+)']

        @web.asynchronous
        def get(self, uri):
            hashed_uri = md5(uri).hexdigest()

            crawler_log_file = '{}.crawl.log'.format(os.path.join(
                self.blueprint.log_dir, hashed_uri))

            with open(crawler_log_file, 'rb') as f:
                for idx, line in enumerate(f.readlines()):
                    if 'crawl-result' in line:
                        json_line = json.loads(line)
                        self.write(json.dumps(json_line['crawl-result']))
                        self.finish()

                if not self._finished:
                    self.write(json.dumps({'error': False}))
                    self.finish()

    class Screenshot(RequestHandler):
        route = ['/damage/screenshot/([^/]+)']

        @web.asynchronous
        def get(self, uri):
            hashed_uri = md5(uri).hexdigest()

            screenshot_file = '{}.png'.format(os.path.join(
                self.blueprint.screenshot_dir, hashed_uri))
            f = Image.open(screenshot_file)
            o = io.BytesIO()
            f.save(o, format="JPEG")
            s = o.getvalue()

            self.set_header('Content-type', 'image/png')
            self.set_header('Content-length', len(s))
            self.write(s)
            self.finish()

    class Damage(RequestHandler):
        route = ['/damage/([^/]+)', '/damage/([^/]+)/([^/]+)']

        @web.asynchronous
        def get(self, uri, fresh="false"):
            self.start_time = datetime.now()

            # since all query string arguments are in unicode, cast fresh to
            # boolean
            if fresh.lower() == 'true': fresh = True
            elif fresh.lower() == 'false': fresh = False
            else: fresh = False

            hashed_url = md5(uri).hexdigest()

            # If fresh == True, do fresh calculation
            if fresh:
                self.do_fresh_calculation(uri, hashed_url)
            else:
                # If there are calculation history, use it
                last_calculation = self.check_calculation_archives(hashed_url)
                if last_calculation:
                    result = last_calculation.result
                    time = last_calculation.response_time

                    self.end_time = datetime.now()

                    result = json.loads(result)
                    result['is_archive'] = True
                    result['archive_time'] = time.isoformat()
                    result['calculation_time'] = (self.end_time - self.start_time).seconds

                    self.write(result)
                    self.finish()
                else:
                    self.do_fresh_calculation(uri, hashed_url)

        def check_calculation_archives(self, hashed_uri):
            last_calculation = database.session.query(MementoModel)\
                .filter(MementoModel.hashed_uri==hashed_uri)\
                .order_by(desc(MementoModel.response_time))\
                .first()

            return last_calculation

        def do_fresh_calculation(self, uri, hashed_url):
            # Instantiate MementoModel
            model = MementoModel()
            model.uri = uri
            model.hashed_uri = hashed_url
            model.request_time = datetime.now()

            # Define path for each arguments of crawl.js
            crawljs_script = os.path.join(
                self.application.settings.get('base_dir'),
                'ext', 'phantomjs', 'crawl.js'
            )
            # Define damage-old.py location
            damage_py_script = os.path.join(
                self.application.settings.get('base_dir'),
                'ext', 'damage.py'
            )

            # Define arguments
            screenshot_file = '{}.png'.format(os.path.join(
                self.blueprint.screenshot_dir, hashed_url))
            html_file = '{}.html'.format(os.path.join(
                self.blueprint.html_dir, hashed_url))
            log_file = '{}.log'.format(os.path.join(
                self.blueprint.log_dir, hashed_url))
            images_log_file = '{}.img.log'.format(os.path.join(
                self.blueprint.log_dir, hashed_url))
            csses_log_file = '{}.css.log'.format(os.path.join(
                self.blueprint.log_dir, hashed_url))
            crawler_log_file = '{}.crawl.log'.format(os.path.join(
                self.blueprint.log_dir, hashed_url))

            # Logger
            f = open(crawler_log_file, 'w')
            f.write('')
            f.close()

            f = open(crawler_log_file, 'a')

            def log_output(out, page=None):
                def write(line):
                    f.write(line + '\n')
                    print('Debug: {}'.format(line))

                    if 'background_color' in line and page:
                        line = json.loads(line)
                        if line['background_color']:
                            page['background_color'] = line['background_color']
                    if 'result' in line:
                        try:
                            self.end_time = datetime.now()
                            line = json.loads(line)

                            result = line['result']
                            result['error'] = False
                            result['is_archive'] = False
                            result['calculation_time'] = (self.end_time - self.start_time)\
                                .seconds

                            result = json.dumps(result)

                            # Write result to db
                            model.response_time = datetime.now()
                            model.result = result
                            database.session.add(model)
                            database.session.commit()

                            self.write(result)
                            self.finish()
                        except (ValueError, KeyError) as e:
                            pass

                if out and hasattr(out, 'readline'):
                    for line in iter(out.readline, b''):
                    #for line in out.readlines():
                        line =  line.strip()
                        write(line)
                else:
                    write(out)

            # Error
            def result_error(err = ''):
                if not self._finished:
                    result = {
                        'error' : True,
                        'message' : err
                    }

                    self.write(json.dumps(result))
                    self.finish()

            # page background-color will be set from phantomjs result
            page = {
                'background_color': 'FFFFFF'
            }

            # Crawl page with phantomjs crawl.js via arguments
            # Equivalent with console:
            #   phantomjs crawl.js <screenshot> <html> <log>
            cmd = Command(['phantomjs', '--ssl-protocol=any', crawljs_script,
                           uri, self.blueprint.cache_dir], log_output)
            err_code = cmd.run(10 * 60, args=(page, ))

            if err_code == 0:
                python = sys.executable

                # Calculate damage with damage-old.py via arguments
                # Equivalent with console:
                #   python damage.py <uri> <cache_dir> <bg>
                cmd = Command([python, damage_py_script, uri,
                               self.blueprint.cache_dir,
                               page['background_color']],
                              log_output)

                err_code = cmd.run(10 * 60)
                if err_code != 0:
                    result_error()
            else:
                result_error()