web: flask db upgrade; flask translate compile; gunicorn chef:app
worker: rq worker chef-tasks
