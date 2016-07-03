import json


# from flask import Flask, Blueprint, request, abort, url_for, current_app
from flask import Blueprint, request, abort, current_app
from flask.ext.security import current_user, auth_token_required
from flask.ext.security.utils import encrypt_password, verify_password
from flask.ext.security.passwordless import send_login_instructions
from flask.ext.security.decorators import _check_token

from utils import get_referrer_host_url, humanify, dictify, send_gmail
from .models import StoryLine
from .item import fetch_item

SAFE_KEYS = ('email', 'name', 'confirmed_at', 'next')

user_endpoints = Blueprint('user', __name__)

@user_endpoints.route('/')
def home():
    if _check_token():
        return humanify({'access': 'private'})
    else:
        return humanify({'access': 'public'})

@user_endpoints.route('/user', methods=['GET', 'POST', 'PUT', 'DELETE'])
@user_endpoints.route('/user/<user_id>', methods=['GET', 'POST', 'PUT', 'DELETE'])
@auth_token_required
def manage_user(user_id=None):
    '''
    Manage user accounts. If routed as /user, gives access only to logged in
    user, else if routed as /user/<user_id>, allows administrative level access
    if the looged in user is in the admin group.
    POST gets special treatment, as there must be a way to register new user.
    '''
    # You can create a new user while not being logged in
    # ToDo: defend this endpoint with rate limiting or similar means
    if request.method == 'POST':
        if not 'application/json' in request.headers['Content-Type']:
            abort(400, "Please set 'Content-Type' header to 'application/json'")
        return user_handler(None, request)

    if user_id:
        # admin access_mode
        if is_admin(current_user):
            return user_handler(user_id, request)
        else:
            current_app.logger.debug('Non-admin user {} tried to access user id {}'.format(
                                                  current_user.email, user_id))
            abort(403)
    else:
        # user access_mode
        user_id = str(current_user.id)
        # Deny POSTing to logged in non-admin users to avoid confusion with PUT
        if request.method == 'POST':
            abort(400, 'POST method is not supported for logged in users.')
        return user_handler(user_id, request)


@user_endpoints.route('/mjs/<item_id>', methods=['DELETE'])
@auth_token_required
def delete_item_from_story(item_id):
    remove_item_from_story(item_id)
    return humanify(get_mjs())
    
@user_endpoints.route('/mjs/<branch_num>/<item_id>', methods=['DELETE'])
@auth_token_required
def remove_item_from_branch(item_id, branch_num=None):
    try:
        branch_num = int(branch_num)
    except ValueError:
        raise BadRequest("branch number must be an integer")

    set_item_in_branch(item_id, branch_num-1, False)
    return humanify(get_mjs())


@user_endpoints.route('/mjs/<branch_num>', methods=['POST'])
@auth_token_required
def add_to_story_branch(branch_num):
    item_id = request.data
    try:
        branch_num = int(branch_num)
    except ValueError:
        raise BadRequest("branch number must be an integer")
    set_item_in_branch(item_id, branch_num-1, True)
    return humanify(get_mjs())


@user_endpoints.route('/mjs/<branch_num>/name', methods=['POST'])
@auth_token_required
def set_story_branch_name(branch_num):

    name = request.data
    current_user.story_branches[int(branch_num)-1] = name
    current_user.save()
    return humanify(get_mjs())


@user_endpoints.route('/mjs', methods=['GET', 'POST'])
@auth_token_required
def manage_jewish_story():
    '''Logged in user may GET or POST their jewish story links.
    the links are stored as an array of items where each item has a special
    field: `branch` with a boolean array indicating which branches this item is
    part of.
    POST requests should be sent with a string in form of "collection_name.id".
    '''
    if request.method == 'GET':
        return humanify(get_mjs(current_user))

    elif request.method == 'POST':
        try:
            data = request.data
            # Enforce mjs structure:
            if not isinstance(data, str):
                abort(400, 'Expecting a string')

        except ValueError:
            e_message = 'Could not decode JSON from data'
            current_app.logger.debug(e_message)
            abort(400, e_message)

        add_to_my_story(data)
        return humanify(get_mjs())

# Ensure we have a user to test with
'''
@current_app.before_first_request
def setup_users():
    for role_name in ('user', 'admin'):
        if not current_app.user_datastore.find_role(role_name):
            current_app.logger.debug('Creating role {}'.format(role_name))
            current_app.user_datastore.create_role(name=role_name)

    user_role = current_app.user_datastore.find_role('user')
    test_user = current_app.user_datastore.get_user('tester@example.com')
    if test_user:
        test_user.delete()
    current_app.logger.debug('Creating test user.')
    current_app.user_datastore.create_user(email='tester@example.com',
                                name='Test User',
                                password=encrypt_password('password'),
                                roles=[user_role])
'''

def is_admin(flask_user_obj):
    if flask_user_obj.has_role('admin'):
        return True
    else:
        return False


def user_handler(user_id, request):
    method = request.method
    data = request.data
    referrer = request.referrer
    if referrer:
        referrer_host_url = get_referrer_host_url(referrer)
    else:
        referrer_host_url = None
    if data:
        try:
            data = json.loads(data)
            if not isinstance(data, dict):
                abort(
                    400,
                    'Only dict like objects are supported for user management')
        except ValueError:
            e_message = 'Could not decode JSON from data'
            current_app.logger.debug(e_message)
            abort(400, e_message)

    if method == 'GET':
        return humanify(get_user(user_id))

    elif method == 'POST':
        if not data:
            abort(400, 'No data provided')
        return humanify(send_ticket(data, referrer_host_url))

    elif method == 'PUT':
        if not data:
            abort(400, 'No data provided')
        return humanify(update_user(user_id, data))

    elif method == 'DELETE':
        return humanify(delete_user(user_id))


def get_user_or_error(user_id):
    user = current_app.user_datastore.get_user(user_id)
    if user:
        return user
    else:
        raise abort(404, 'User not found')


def clean_user(user_obj):
    user_dict = dictify(user_obj)
    ret = {}
    for key in SAFE_KEYS:
        ret[key] = user_dict.get(key, None)
    ret.update(get_mjs(user_obj))
    return ret


def get_user(user_id):
    user_obj = get_user_or_error(user_id)
    return clean_user(user_obj)


def delete_user(user_id):
    user = get_user_or_error(user_id)
    if is_admin(user):
        return {'error': 'God Mode!'}
    else:
        user.delete()
        return {}


def send_ticket(user_dict, referrer_host_url=None):
    next = getattr(user_dict, 'next', '/welcome')
    try:
        email = user_dict['email']
        # enc_password = encrypt_password(user_dict['password'])
    except KeyError as e:
        e_message = '{} key is missing from data'.format(e)
        current_app.logger.debug(e_message)
        abort(400, e_message)

    user = current_app.user_datastore.get_user(email)
    if not user:
        user = current_app.user_datastore.create_user(email=email, next=next)
        # Add default role to a newly created user
        current_app.user_datastore.add_role_to_user(user, 'user')

    send_login_instructions(user)
    return clean_user(user)


def update_user(user_id, user_dict):
    user_obj = get_user_or_error(user_id)
    if 'email' in user_dict.keys():
        user_obj.email = user_dict['email']
    if 'name' in user_dict.keys():
        user_obj.name = user_dict['name']

    user_obj.save()
    return clean_user(user_obj)


def get_frontend_activation_link(user_id, referrer_host_url):
    s = URLSafeSerializer(current_app.secret_key)
    payload = s.dumps(user_id)
    return '{}/verify_email/{}'.format(referrer_host_url, payload)


def send_activation_email(user_id, referrer_host_url):
    user = get_user_or_error(user_id)
    email = user.email
    name = user.name
    activation_link = get_frontend_activation_link(user_id, referrer_host_url)
    body = _generate_confirmation_body('email_verfication_template.html',
                                       name, activation_link)
    subject = 'My Jewish Story: please confirm your email address'
    sent = send_gmail(subject, body, email, message_mode='html')
    if not sent:
        e_message = 'There was an error sending an email to {}'.format(email)
        current_app.logger.error(e_message)
        abort(500, e_message)
    return humanify({'sent': email})


def _generate_confirmation_body(template_fn, name, activation_link):
    try:
        fh = open(template_fn)
        template = fh.read()
        fh.close()
        return template.format(name, activation_link)
    except:
        current_app.logger.debug("Couldn't open template file {}".format(template_fn))
        abort(500, "Couldn't open template file")

    body = '''Hello {}!
    Please click on <a href="{}">activation link</a> to activate your user at My Jewish Story web site.
    If you received this email by mistake, simply delete it.

    Thanks, Beit HaTfutsot Online team.'''
    return body.format(name, activation_link)

def add_to_my_story(item_id):
    current_user.story_items.append(StoryLine(id=item_id,
                                              in_branch=4*[False]))
    current_user.save()

def get_mjs(user=current_user):
    return {'story_items': [{'id': o.id, 'in_branch': o.in_branch} for o in user.story_items],
            'story_branches': user.story_branches}

def set_item_in_branch(item_id, branch_num, value):
    line = None
    for i in current_user.story_items:
        if i.id == item_id:
            line = i
            break
    if not line:
        abort(400, 'item must be part of the story'.format(item_id))
    line.in_branch[branch_num] = value
    current_user.save()

def remove_item_from_story(item_id):
    current_user.story_items = [i for i in current_user.story_items if i.id != item_id]
    current_user.save()

def collect_editors_items(name):
    """ 
        look for a branch named `name` in all editors stories, collect the items
        and return them
    """
    editor_role = current_app.user_datastore.find_role('editor')
    editors = current_app.user_datastore.user_model.objects(roles=editor_role,
                                                            story_branches=name)
    items = []
    for user in editors:
        i = user.story_branches.index(name)
        for j in user.story_items:
            if j.in_branch[i]:
                items.append(fetch_item(j.id))
    return items
