from datetime import datetime
from flask import render_template, flash, redirect, url_for, request, g, \
    jsonify, current_app, Markup
from flask_login import current_user, login_required
from flask_babel import _, get_locale
from guess_language import guess_language
from app import db
from app.main.forms import EditProfileForm, PostForm, SearchForm, MessageForm, TodoCreateForm
from app.models import User, Post, Message, Notification, Todo
from app.translate import translate
from app.main import bp


@bp.before_app_request
def before_request():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.utcnow()
        db.session.commit()
        g.search_form = SearchForm()
    g.locale = str(get_locale())


@bp.route('/')
@bp.route('/index')
@login_required
def index():

    page = request.args.get('page', 1, type=int)
    posts = Post.query.order_by(Post.timestamp.desc()).paginate(
        page, current_app.config['POSTS_PER_PAGE'], False)
    next_url = url_for('main.index', page=posts.next_num) \
        if posts.has_next else None
    prev_url = url_for('main.index', page=posts.prev_num) \
        if posts.has_prev else None
    todo_list = Todo.query.filter(Todo.assigned_to_user_id == current_user.id, Todo.priority <= 3).all()
    return render_template('index.html', title=_('Home'),
                           posts=posts.items, next_url=next_url,
                           prev_url=prev_url, todo_list=todo_list)


@bp.route('/explore', methods=['GET', 'POST'])
@login_required
def explore():
    form = PostForm()
    if form.validate_on_submit():
        language = guess_language(form.post.data)
        if language == 'UNKNOWN' or len(language) > 5:
            language = ''
        post = Post(body=form.post.data, author=current_user, language=language)
        db.session.add(post)
        db.session.commit()
        flash(_('Your post is now live!'))
        return redirect(url_for('main.index'))
    page = request.args.get('page', 1, type=int)
    posts = Post.query.order_by(Post.timestamp.desc()).paginate(
        page, current_app.config['POSTS_PER_PAGE'], False)
    next_url = url_for('main.explore', page=posts.next_num) \
        if posts.has_next else None
    prev_url = url_for('main.explore', page=posts.prev_num) \
        if posts.has_prev else None
    return render_template('index.html', title=_('Posts'), form=form,
                           posts=posts.items, next_url=next_url,
                           prev_url=prev_url)


@bp.route('/user/<username>')
@login_required
def user(username):
    user = User.query.filter_by(username=username).first_or_404()
    page = request.args.get('page', 1, type=int)
    posts = user.posts.order_by(Post.timestamp.desc()).paginate(
        page, current_app.config['POSTS_PER_PAGE'], False)
    next_url = url_for('main.user', username=user.username,
                       page=posts.next_num) if posts.has_next else None
    prev_url = url_for('main.user', username=user.username,
                       page=posts.prev_num) if posts.has_prev else None
    return render_template('user.html', user=user, posts=posts.items,
                           next_url=next_url, prev_url=prev_url)


@bp.route('/user/<username>/popup')
@login_required
def user_popup(username):
    user = User.query.filter_by(username=username).first_or_404()
    return render_template('user_popup.html', user=user)


@bp.route('/edit_profile', defaults={'username': ''}, methods=['GET', 'POST'])
@bp.route('/edit_profile/<username>', methods=['GET', 'POST'])
@login_required
def edit_profile(username):
    if not current_user.is_parent:
        return redirect(url_for('main.user', username=username))
    if username:
        user = User.query.filter_by(username=username).first_or_404()
    else:
        user = current_user
    form = EditProfileForm(user.username)
    if form.validate_on_submit():
        user.username = form.username.data
        user.about_me = form.about_me.data
        user.is_parent = form.is_parent.data
        db.session.commit()
        flash(_('Your changes have been saved.'))
        return redirect(url_for('main.edit_profile', username=user.username))
    elif request.method == 'GET':
        form.username.data = user.username
        form.about_me.data = user.about_me
        form.is_parent.data = user.is_parent
    return render_template('edit_profile.html', title=_('Edit Profile'), user=user,
                           form=form)


@bp.route('/follow/<username>')
@login_required
def follow(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash(_('User %(username)s not found.', username=username))
        return redirect(url_for('main.index'))
    if user == current_user:
        flash(_('You cannot follow yourself!'))
        return redirect(url_for('main.user', username=username))
    current_user.follow(user)
    db.session.commit()
    flash(_('You are following %(username)s!', username=username))
    return redirect(url_for('main.user', username=username))


@bp.route('/unfollow/<username>')
@login_required
def unfollow(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash(_('User %(username)s not found.', username=username))
        return redirect(url_for('main.index'))
    if user == current_user:
        flash(_('You cannot unfollow yourself!'))
        return redirect(url_for('main.user', username=username))
    current_user.unfollow(user)
    db.session.commit()
    flash(_('You are not following %(username)s.', username=username))
    return redirect(url_for('main.user', username=username))


@bp.route('/translate', methods=['POST'])
@login_required
def translate_text():
    return jsonify({'text': translate(request.form['text'],
                                      request.form['source_language'],
                                      request.form['dest_language'])})


@bp.route('/search')
@login_required
def search():
    if not g.search_form.validate():
        return redirect(url_for('main.explore'))
    page = request.args.get('page', 1, type=int)
    posts, total = Post.search(g.search_form.q.data, page,
                               current_app.config['POSTS_PER_PAGE'])
    next_url = url_for('main.search', q=g.search_form.q.data, page=page + 1) \
        if total > page * current_app.config['POSTS_PER_PAGE'] else None
    prev_url = url_for('main.search', q=g.search_form.q.data, page=page - 1) \
        if page > 1 else None
    return render_template('search.html', title=_('Search'), posts=posts,
                           next_url=next_url, prev_url=prev_url)


@bp.route('/send_message/<recipient>', methods=['GET', 'POST'])
@login_required
def send_message(recipient):
    user = User.query.filter_by(username=recipient).first_or_404()
    form = MessageForm()
    if form.validate_on_submit():
        msg = Message(author=current_user, recipient=user,
                      body=form.message.data)
        db.session.add(msg)
        user.add_notification('unread_message_count', user.new_messages())
        db.session.commit()
        flash(_('Your message has been sent.'))
        return redirect(url_for('main.user', username=recipient))
    return render_template('send_message.html', title=_('Send Message'),
                           form=form, recipient=recipient)


@bp.route('/messages')
@login_required
def messages():
    current_user.last_message_read_time = datetime.utcnow()
    current_user.add_notification('unread_message_count', 0)
    db.session.commit()
    page = request.args.get('page', 1, type=int)
    messages = current_user.messages_received.order_by(
        Message.timestamp.desc()).paginate(
            page, current_app.config['POSTS_PER_PAGE'], False)
    next_url = url_for('main.messages', page=messages.next_num) \
        if messages.has_next else None
    prev_url = url_for('main.messages', page=messages.prev_num) \
        if messages.has_prev else None
    return render_template('messages.html', messages=messages.items,
                           next_url=next_url, prev_url=prev_url)


@bp.route('/export_posts')
@login_required
def export_posts():
    if current_user.get_task_in_progress('export_posts'):
        flash(_('An export task is currently in progress'))
    else:
        current_user.launch_task('export_posts', _('Exporting posts...'))
        db.session.commit()
    return redirect(url_for('main.user', username=current_user.username))


@bp.route('/notifications')
@login_required
def notifications():
    since = request.args.get('since', 0.0, type=float)
    notifications = current_user.notifications.filter(
        Notification.timestamp > since).order_by(Notification.timestamp.asc())
    return jsonify([{
        'name': n.name,
        'data': n.get_data(),
        'timestamp': n.timestamp
    } for n in notifications])


@bp.route('/todo_list', defaults={'username': ''})
@bp.route('/todo_list/<username>')
@login_required
def todo_list(username):
    show_completed = request.args.get('show_completed', False, type=bool)
    user = User.query.filter_by(username=username).first()
    qry = Todo.query
    if not show_completed:
        qry = qry.filter(Todo.completed.is_(False))
    if user:
        qry = qry.filter(Todo.assigned_to_user_id == user.id)
    todo_list = qry.order_by(Todo.priority).all()
    # TODO: paginate
    return render_template('todo_list.html', todo_list=todo_list, username=username, show_completed=show_completed)


@bp.route('/todo/<id>')
@login_required
def todo(id):
    todo = Todo.query.filter(Todo.id == id).first_or_404()
    return render_template('todo.html', todo=todo)


@bp.route('/todo/<id>/set_done/<completed>')
@login_required
def todo_done(id, completed):
    if not current_user.is_parent:
        flash(_('Only parents can update tasks'))
        return redirect(url_for('main.todo', id=id))
    todo = Todo.query.filter(Todo.id == id).first()
    if todo is None:
        flash(_('Todo with id %(id)s not found.', id=id))
        return redirect(url_for('main.todo', id=id))
    todo.completed = bool(int(completed))
    todo.assigned_to.score = 1
    db.session.commit()
    if completed:
        flash(_('Task %(name)s is done', name=todo.name))
    else:
        flash(_('Task %(name)s is set back to todo', name=todo.name))
    return redirect(url_for('main.todo_list', username=current_user.username))


@bp.route('/todo/<id>/delete')
@login_required
def todo_delete(id):
    iamsure = request.args.get('iamsure', False, type=bool)
    if not current_user.is_parent:
        flash(_('Only parents can update tasks'))
        return redirect(url_for('main.todo', id=id))
    todo = Todo.query.filter(Todo.id == id).first()
    if todo is None:
        flash(_('Todo with id %(id)s not found.', id=id))
        return redirect(url_for('main.todo', id=id))
    if bool(int(iamsure)):
        db.session.delete(todo)
        db.session.commit()
        flash(_('Task %(name)s is deleted', name=todo.name))
        return redirect(url_for('main.todo_list', username=current_user.username))
    else:
        delete_url = url_for('main.todo_delete', id=id)
        cancel_url = url_for('main.todo', id=id)
        flash(_(Markup('Are you sure you want to delete task "%(name)s"? This can not be undone!<br><br> '
                       '<a href="%(delete_url)s?iamsure=1">Yes</a> or <a href="%(cancel_url)s">No</a>'),
                name=todo.name, delete_url=delete_url, cancel_url=cancel_url))
        return redirect(url_for('main.todo', id=todo.id))


@bp.route('/todo_create', methods=['GET', 'POST'])
@login_required
def todo_create():
    form = TodoCreateForm()
    form.assigned_to_user_id.choices = [(u.id, u.username) for u in User.query.order_by('username')]
    form.assigned_to_user_id.default = current_user.id
    if form.validate_on_submit():
        todo = Todo(name=form.name.data, description=form.description.data, assigned_by_user_id=current_user.id,
                    assigned_to_user_id=form.assigned_to_user_id.data, priority=form.priority.data,
                    score=form.score.data)
        db.session.add(todo)
        db.session.commit()
        flash(_('Task %s Added' % form.name.data))
        return redirect(url_for('main.todo_list', username=current_user.username))
    return render_template('todo_create.html', form=form)


@bp.route('/todo_edit/<id>', methods=['GET', 'POST'])
@login_required
def todo_edit(id):
    todo = Todo.query.filter(Todo.id == id).first()
    if todo is None:
        flash(_('Todo with id %(id)s not found.', id=id))
        return redirect(url_for('main.todo', id=id))
    form = TodoCreateForm()
    form.assigned_to_user_id.choices = [(u.id, u.username) for u in User.query.order_by('username')]
    form.assigned_to_user_id.default = current_user.id
    if form.validate_on_submit():
        todo.name = form.name.data
        todo.description = form.description.data
        todo.assigned_to_user_id = form.assigned_to_user_id.data
        todo.priority = form.priority.data
        todo.score = form.score.data
        db.session.commit()
        flash(_('Task %s updated' % form.name.data))
        return redirect(url_for('main.todo_list', username=current_user.username))
    elif request.method == 'GET':
        form.name.data = todo.name
        form.description.data = todo.description
        form.assigned_to_user_id.data = todo.assigned_to_user_id
        form.priority.data = todo.priority
        form.score.data = todo.score

    return render_template('todo_edit.html', form=form)
