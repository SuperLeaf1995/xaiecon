#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# Module that allows displaying Terms of service, content policy and
# privacy policy.
#

from flask import Blueprint, render_template
from flask_babel import gettext

from xaiecon.modules.core.cache import cache

from xaiecon.modules.core.wrappers import login_wanted

legal = Blueprint('legal',__name__,template_folder='templates/legal')

@legal.route('/legal/content', methods = ['GET'])
@login_wanted
@cache.memoize(timeout=86400)
def display_content(u=None):
	return render_template('legal/content_policy.html',u=u,title='Content Policy')

@legal.route('/legal/terms', methods = ['GET'])
@login_wanted
@cache.memoize(timeout=86400)
def display_terms(u=None):
	return render_template('legal/terms_of_service.html',u=u,title='Terms of Service')

@legal.route('/legal/privacy', methods = ['GET'])
@login_wanted
@cache.memoize(timeout=86400)
def display_privacy(u=None):
	return render_template('legal/privacy_policy.html',u=u,title='Privacy Policy')

print('Legal pages ... ok')
