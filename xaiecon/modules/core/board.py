#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# Board module, place where posts can be put and yanked off
#

import PIL
import secrets
import os
import threading
import requests
import time
import random

from flask import Blueprint, render_template, redirect, request, abort, send_from_directory
from flask_babel import gettext
from werkzeug.utils import secure_filename

from xaiecon.classes.base import open_db
from xaiecon.classes.board import Board, BoardBan, BoardSub
from xaiecon.classes.post import Post
from xaiecon.classes.category import Category
from xaiecon.classes.user import User
from xaiecon.classes.exception import XaieconException

from xaiecon.modules.core.limiter import limiter
from xaiecon.modules.core.wrappers import login_wanted, login_required

from sqlalchemy.orm import joinedload
from sqlalchemy import desc, asc

board = Blueprint('board',__name__,template_folder='templates')

@board.route('/board/view/<bid>', methods = ['GET'])
@board.route('/board/view/<bid>/<sort>', methods = ['GET'])
@login_wanted
def view(u=None,bid=0,sort='new'):
	db = open_db()
	board = db.query(Board).filter_by(id=bid).options(joinedload('*')).first()
	if board is None:
		abort(404)
	posts = db.query(Post).filter_by(board_id=board.id).options(joinedload('*'))
	
	if sort == 'new':
		posts = posts.order_by(desc(Post.id))
	elif sort == 'old':
		posts = posts.order_by(asc(Post.id))
	else:
		abort(401)
	
	posts = posts.all()
	
	db.close()
	return render_template('board/view.html',u=u,title=board.name,board=board,posts=posts)

# Compatibility with stuff
@board.route('/+<name>', methods = ['GET'])
@board.route('/!<name>', methods = ['GET'])
@board.route('/r/<name>', methods = ['GET'])
@board.route('/v/<name>', methods = ['GET'])
@board.route('/p/<name>', methods = ['GET'])
@board.route('/s/<name>', methods = ['GET'])
@board.route('/c/<name>', methods = ['GET'])
@board.route('/b/<name>', methods = ['GET'])
@login_wanted
def view_by_name(u=None,name=None):
	db = open_db()
	board = db.query(Board).filter(Board.name.ilike(name)).options(joinedload('*')).all()
	if board is None:
		abort(404)
	db.close()
	
	# Multiple boards
	if len(board) > 1:
		random.shuffle(board)
		return render_template('board/pick.html',u=u,title=name,boards=board)
	
	# Only 1 board exists with that name
	return redirect(f'/board/view/{board[0].id}')

@board.route('/board/edit/<bid>', methods = ['GET','POST'])
@login_required
def edit(u=None,bid=0):
	try:
		db = open_db()
		
		board = db.query(Board).filter_by(id=bid).first()
		if board is None:
			abort(404)

		if u.can_make_board == False:
			raise XaieconException('You cannot edit or make boards')	
		
		if request.method == 'POST':
			name = request.values.get('name')
			descr = request.values.get('descr')
			category = request.values.get('category')
			keywords = request.values.get('keywords')
			
			if u.mods(board.id) == False:
				raise XaieconException('Not authorized')
			
			category = db.query(Category).filter_by(name=category).first()
			if category is None:
				raise XaieconException('Not a valid category')

			file = request.files['icon']
			if file:
				# Remove old image
				if board.has_icon == True:
					try:
						os.remove(os.path.join('user_data',board.icon_file))
					except FileNotFoundError:
						pass

				# Create thumbnail
				filename = f'{secrets.token_hex(32)}.jpeg'
				filename = secure_filename(filename)
				final_filename = os.path.join('user_data',filename)
				file.save(final_filename)

				image = PIL.Image.open(final_filename)
				image = image.convert('RGB')
				image.thumbnail((120,120))
				os.remove(final_filename)
				image.save(final_filename)

				db.query(Board).filter_by(id=bid).update({'icon_file':filename,'has_icon':True})

				csam_thread = threading.Thread(target=csam_check_profile, args=(bid,))
				csam_thread.start()
			else:
				db.query(Board).filter_by(id=bid).update({'has_icon':False})

			db.query(Board).filter_by(id=bid).update({'name':name,'descr':descr,
				'category_id':category.id,'keywords':keywords})
			db.commit()
			
			db.close()
			return redirect(f'/board/view/{bid}')
		else:
			category = db.query(Category).all()
			db.close()
			return render_template('board/edit.html',u=u,title = 'New board',categories=category,board=board)
	except XaieconException as e:
		db.close()
		return render_template('user_error.html',u=u,title = 'Whoops!',err=e)

@board.route('/board/ban/<bid>/<uid>', methods = ['POST','GET'])
@login_required
def ban(u=None,bid=0,uid=0):
	if request.method == 'POST':
		db = open_db()

		reason = request.values.get('reason','No reason specified')

		if u.mods(bid) == False:
			return '',401

		# Board does not exist
		if db.query(Board).filter_by(id=bid).first() is None:
			return '',404
		# Already banned
		if db.query(BoardBan).filter_by(user_id=uid,board_id=bid).first() is not None:
			return '',400
		# Do not ban self
		if uid == u.id:
			return '',400

		sub = BoardBan(user_id=uid,board_id=bid,reason=reason)
		db.add(sub)
		db.commit()

		db.close()
		return redirect(f'/board/view/{bid}')
	else:
		return render_template('board/ban.html',u=u,title='Ban user',bid=bid,uid=uid)

@board.route('/board/unban/<bid>/<uid>', methods = ['POST'])
@login_required
def unban(u=None,bid=0,uid=0):
	db = open_db()
	
	if u.mods(bid) == False:
		return '',401
	
	# Board does not exist
	if db.query(Board).filter_by(id=bid).first() is None:
		return '',404
	# Do not unban self
	if uid == u.id:
		return '',400
	
	db.qeury(BoardBan).filter_by(user_id=uid,board_id=bid).delete()
	db.commit()
	
	db.close()
	return '',200

@board.route('/board/thumb/<bid>', methods = ['GET','POST'])
@login_wanted
@limiter.exempt
def thumb(u=None,bid=0):
	db = open_db()
	board = db.query(Board).filter_by(id=bid).first()
	if board is None:
		abort(404)
	db.close()
	if board.icon_file is None or board.icon_file == '':
		return send_from_directory('assets/public/pics',board.fallback_thumb)
	#if os.path.isfile(os.path.join('./user_data',board.icon_file)) == False:
	#	return send_from_directory('assets/public/pics',board.fallback_thumb)
	return send_from_directory('../user_data',board.icon_file)

@board.route('/board/subscribe/<bid>', methods = ['POST'])
@login_required
def subscribe(u=None,bid=0):
	db = open_db()
	
	# Board does not exist
	if db.query(Board).filter_by(id=bid).first() is None:
		db.close()
		return '',404
	# Already subscribed
	if u.is_subscribed(bid) == True:
		db.close()
		return '',400

	sub = BoardSub(user_id=u.id,board_id=bid)
	db.add(sub)
	
	board = db.query(Board).filter_by(id=bid).first()
	db.query(Board).filter_by(id=bid).update({
		'sub_count':board.sub_count+1})
	
	db.commit()

	db.close()
	return '',200

@board.route('/board/unsubscribe/<bid>', methods = ['POST'])
@login_required
def unsubscribe(u=None,bid=0):
	db = open_db()
	
	# Board does not exist
	if db.query(Board).filter_by(id=bid).first() is None:
		db.close()
		return '',404
	# Not subscribed
	if u.is_subscribed(bid) == False:
		db.close()
		return '',400
	
	db.query(BoardSub).filter_by(user_id=u.id,board_id=bid).delete()
	
	board = db.query(Board).filter_by(id=bid).first()
	db.query(Board).filter_by(id=bid).update({
		'sub_count':board.sub_count-1})
	
	db.commit()
	
	db.close()
	return '',200

@board.route('/board/new', methods = ['GET','POST'])
@login_required
@limiter.limit('15/minute')
def new(u=None):
	try:
		db = open_db()

		if u.can_make_board == False:
			raise XaieconException('You are not allowed to make boards')

		if request.method == 'POST':
			name = request.values.get('name')
			descr = request.values.get('descr')
			category = request.values.get('category')
			keywords = request.values.get('keywords')
			
			if db.query(Board).filter_by(user_id=u.id).count() > 50:
				raise XaieconException('Limit of 50 boards reached')
			
			category = db.query(Category).filter_by(name=category).first()
			if category is None:
				raise XaieconException('Not a valid category')
			
			pics = ['board.png']
			
			board = Board(
				name=name,
				descr=descr,
				user_id=u.id,
				category_id=category.id,
				keywords=keywords,
				fallback_thumb=random.choice(pics))
			
			db.add(board)
			db.commit()
			
			db.refresh(board)
			
			db.close()
			return redirect(f'/board/view/{board.id}')
		else:
			category = db.query(Category).all()
			db.close()
			return render_template('board/new.html',u=u,title = 'New board',categories=category)
	except XaieconException as e:
		db.close()
		return render_template('user_error.html',u=u,title = 'Whoops!',err=e)

# Check user for csam, if so ban the user
def csam_check_profile(bid: int):
	db = open_db()

	# Let's see if this is csam
	board = db.query(Board).filter_by(id=bid).first()

	headers = {'User-Agent':'xaiecon-csam-check'}

	for i in range(10):
		x = requests.get(f'https://{os.environ.get("DOMAIN_NAME")}/board/thumb/{bid}',headers=headers)
		if x.status_code in [200, 451]:
			break
		else:
			time.sleep(10)
	
	if x.status_code != 451:
		return

	# Ban user
	db.query(User).filter_by(id=board.user_id).update({
		'ban_reason':'CSAM Automatic Removal',
		'is_banned':True})

	# Ban board
	db.query(Board).filter_by(id=board.id).update({
		'ban_reason':'CSAM Automatic Removal',
		'is_banned':True})
	db.commit()
	os.remove(os.path.join('user_data',board.image_file))
	db.close()
	return

print('Board pages ... ok')
