import logging
import os
import inspect
from datetime import timedelta
import pymongo
import elasticsearch
from flask import Flask
from flask.ext.mongoengine import MongoEngine
from flask.ext.cors import CORS
from flask.ext.mail import Mail
from flask.ext.security import Security, MongoEngineUserDatastore
from bhs_common.utils import get_conf
from bhs_api.utils import get_logger

SEARCH_CHUNK_SIZE = 15
CONF_FILE = '/etc/bhs/config.yml'
# Create app
def create_app(testing=False, live=False):
    from bhs_api.models import User, Role
    from bhs_api.forms import LoginForm

    app = Flask(__name__)
    app.testing = testing

    # Get configuration from file
    must_have_keys = set(['secret_key',
                        'mail_server',
                        'mail_port',
                        'user_db_host',
                        'user_db_port',
                        'elasticsearch_host',
                        'user_db_name',
                        'data_db_host',
                        'data_db_port',
                        'data_db_name',
                        'image_bucket_url',
                        'video_bucket_url'])

    # load the conf file. use local copy if nothing in the system
    if os.path.exists(CONF_FILE):
        conf = get_conf(CONF_FILE, must_have_keys)
    else:
        current_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe()))) # script directory
        conf = get_conf(os.path.join(current_dir, 'conf', 'bhs_config.yaml'),
                        must_have_keys)

    # Our config - need to move everything here
    app.config['VIDEO_BUCKET_URL'] = "https://storage.googleapis.com/bhs-movies"
    app.config['IMAGE_BUCKET_URL'] = "https://storage.googleapis.com/bhs-flat-pics"

    # Set app config
    app.config['DEBUG'] = True
    app.config['FRONTEND_SERVER'] = conf.frontend_server
    # Security Config
    app.config['SECRET_KEY'] = conf.secret_key
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SECURITY_PASSWORDLESS'] = True
    app.config['SECURITY_EMAIL_SENDER'] = 'support@bh.org.il'
    app.config['SECURITY_USER_IDENTITY_ATTRIBUTES'] = 'email'
    app.config['SECURITY_EMAIL_SUBJECT_PASSWORDLESS'] = 'Login link for your jewish story'
    app.config['SECURITY_POST_LOGIN_VIEW'] = '/mjs'
    # Mail Config
    app.config['MAIL_SERVER'] = conf.mail_server
    app.config['MAIL_PORT'] = conf.mail_port
    # Mail optional username and password
    try:
        app.config['MAIL_USERNAME'] = conf.mail_username
        app.config['MAIL_PASSWORD'] = conf.mail_password
    except AttributeError:
        pass

    # DB Config
    app.config['MONGODB_DB'] = conf.user_db_name
    app.config['MONGODB_HOST'] = conf.user_db_host
    app.config['MONGODB_PORT'] = conf.user_db_port

    app.mail = Mail(app)
    app.db = MongoEngine(app)
    app.user_datastore = MongoEngineUserDatastore(app.db, User, Role)
    app.security = Security(app, app.user_datastore,
                            passwordless_login_form=LoginForm)
    # Create database connection object
    app.client_data_db = pymongo.MongoClient(conf.data_db_host, conf.data_db_port,
                    read_preference=pymongo.ReadPreference.SECONDARY_PREFERRED)
    app.data_db = app.client_data_db[conf.data_db_name]

    # Create the elasticsearch connection
    app.es = elasticsearch.Elasticsearch(conf.elasticsearch_host)
    # Add the views
    from bhs_api.views import blueprint, autodoc
    app.register_blueprint(blueprint)
    # Initialize autodoc - https://github.com/acoomans/flask-autodoc
    autodoc.init_app(app)
    #allow CORS
    cors = CORS(app, origins=['*'], headers=['content-type', 'accept',
                                            'authentication-token', 'Authorization'])
    # logging
    if live:
        app.config['PROPAGATE_EXCEPTIONS'] = True
        try:
            fh = logging.FileHandler(conf.log_file)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            fh.setFormatter(formatter)
            app.logger.addHandler(fh)
        except AttributeError:
            pass

    app.logger.debug("Hellow world")

    return app, conf

# Specify the bucket name for user generated content
ugc_bucket = 'bhs-ugc'

# Specify the email address of the editor for UGC moderation
editor_address = 'inna@bh.org.il,bennydaon@bh.org.il'
