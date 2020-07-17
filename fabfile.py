"""AnimeSuki Fabric deployment script"""

import os
import configparser
import json
import logging
import sys
from datetime import datetime

from fabric import task


logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s] %(levelname)s %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S',
                    stream=sys.stdout)
logger = logging.getLogger(__name__)

# Load configuration from INI-like .env file
config = configparser.ConfigParser()
config.read(os.path.join(os.path.join(os.path.dirname(__file__), '.env')))


hosts = json.loads(config.get('fabric', 'hosts'))
repository = 'https://github.com/ghdpro/animesuki.git'
user = 'animesuki'
home = f'/home/{user}'
builds = f'{home}/builds'
venv = f'{home}/venv'
dump = f'{home}/dump'


@task(hosts=hosts)
def deploy(c):
    # Get latest commit ID
    rev = c.local('git rev-parse --short HEAD', timeout=1, hide=True).stdout.strip()
    _clone(c, rev)
    _venv(c, rev)
    _generate_id(c, rev)
    _backup_db(c)
    _migrate(c, rev)
    _update_symlinks(c, rev)
    _reload(c)


@task(hosts=hosts)
def init(c):
    """Initializes project"""
    logger.info('Initializing project...')
    rev = 'current'
    _backup_db(c)
    with c.cd(f'{builds}/{rev}'), c.prefix(f'source {venv}/{rev}/bin/activate'):
        c.run(f'python3 manage.py migrate', echo=True)
        c.run(f'python3 manage.py loaddata sites', echo=True)
        c.run(f'python3 manage.py loaddata language', echo=True)


def _clone(c, rev):
    """"Clone current build"""
    logger.info('Cloning current build...')
    c.run(f'mkdir -p {builds}', echo=True)
    with c.cd(builds):
        c.run(f'rm -r -f {rev}', echo=True)
        # The following command will fail if latest commit wasn't pushed to remote before running this script
        c.run(f'git clone {repository} {rev}', echo=True)
    # Create symlink for .env file
    with c.cd(f'{builds}/{rev}/'):
        c.run(f'ln -s {home}/.env .env ', echo=True)


def _venv(c, rev):
    """Create virtualenv & install all requirements"""
    c.run(f'mkdir -p {venv}', echo=True)
    with c.cd(venv):
        logger.info('Creating virtualenv...')
        c.run(f'rm -r -f {rev}', echo=True)
        c.run(f'python3 -m venv {rev}', echo=True)
    with c.prefix(f'source {venv}/{rev}/bin/activate'):
        logger.info('Installing requirements...')
        c.run(f'pip install -Uq pip', echo=True)
        c.run(f'pip install -Uq setuptools', echo=True)
        c.run(f'pip install -Uqr {builds}/{rev}/requirements.txt', echo=True)


def _backup_db(c):
    logger.info('Creating database backup...')
    # Make database backup before proceeding with operations that might mess with the database
    c.run(f'mkdir -p {dump}', echo=True)
    # This command assumes correctly configured .pgpass file is present
    # Note that this database backup uses the custom format; use pg_restore to restore
    with c.cd(dump):
        c.run(f'pg_dump -U animesuki -Fc animesuki > animesuki-{datetime.now().strftime("%Y-%m-%d-%H%M")}.dump', echo=True)


def _migrate(c, rev):
    with c.cd(f'{builds}/{rev}'), c.prefix(f'source {venv}/{rev}/bin/activate'):
        # Collect static files
        logger.info('Collecting static files...')
        c.run(f'python3 manage.py collectstatic --clear --no-input', echo=True)
        # Run migrations
        logger.info('Migrating database...')
        c.run(f'python3 manage.py migrate', echo=True)
        # Run tests
        logger.info('Running tests....')
        c.run(f'python3 manage.py test --keepdb', echo=True)
        # Run check
        logger.info('Running check....')
        c.run(f'python3 manage.py check --deploy', echo=True)


def _update_symlinks(c, rev):
    """Updates 'current' symlinks"""
    logger.info('Updating "current" symlinks...')
    with c.cd(builds):
        c.run(f'rm -r -f current', echo=True)
        c.run(f'ln -s {rev} current', echo=True)
    with c.cd(venv):
        c.run(f'rm -r -f current', echo=True)
        c.run(f'ln -s {rev} current', echo=True)


def _generate_id(c, rev):
    """Generates a small template with commit number, id string and date"""
    logger.info('Generating version information...')
    count = c.local('git rev-list --count HEAD', timeout=1, hide=True)
    id_file = "{}/templates/id.html".format(os.path.dirname(__file__))
    # Date is always the deployment date, assumes the latest commit was made the same day
    output = f'Version {count.stdout.strip()}:{rev} ({datetime.now().date().isoformat()})'
    c.local(f'echo "{output}" > {id_file}', timeout=1, echo=True)
    c.put(id_file, f'{builds}/{rev}/templates/')


def _reload(c):
    logger.info('Reloading services...')
    # Reload services - requires properly configured sudoers file
    c.run('sudo service uwsgi reload', echo=True)
    c.run('sudo service nginx reload', echo=True)
