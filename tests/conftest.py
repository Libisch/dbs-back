# -*- coding: utf-8 -*-
import elasticsearch
import sys
import os
import json

import pytest
import mock
from pytest_flask.plugin import client, config
import mongomock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__),
                                             os.pardir)))

from bhs_api import create_app


@pytest.fixture
def get_auth_header(app, tester):
    return {'Authentication-Token': tester.get_auth_token()}



@pytest.fixture(scope="session")
def app():
    mock.patch('elasticsearch.Elasticsearch')
    app, conf = create_app(testing=True)
    return app


@pytest.fixture(scope="session")
def tester(app):
    user = app.user_datastore.get_user("tester@example.com")
    if user:
        app.user_datastore.delete_user(user)

    user = app.user_datastore.create_user(email='tester@example.com',
                                    name={'en': 'Test User'})
    return user


@pytest.fixture
def tester_headers(client, get_auth_header):
    headers = {'Content-Type': 'application/json'}
    headers.update(get_auth_header)
    return headers


@pytest.fixture
def mock_db():
    items = [{'UnitId': '1',
              'Slug': {'En': 'personality_tester',
                       'He': u'אישיות_בודק',
                      },
              'StatusDesc': 'Completed',
              'RightsDesc': 'Full',
              'DisplayStatusDesc':  'free',
              'UnitText1': {'En': 'tester',
                            'He': 'בודק',
                            }
             },
             {'UnitId': '2',
              'Slug': {'En': 'personality_another-tester',
                       'He': u'אישיות_עוד-בודק',
                      },
              'StatusDesc': 'Edit',
              'RightsDesc': 'Full',
              'DisplayStatusDesc':  'free',
              'UnitText1': {'En': 'another tester',
                            'He': 'עוד בודק',
                            }
             }]
    db = mongomock.MongoClient().db
    persons = db.create_collection('personalities')
    for item in items:
        item['_id'] = persons.insert(item)
    return db

