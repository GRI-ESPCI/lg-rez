import traceback
import tools

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config.from_pyfile('../config.py')
db = SQLAlchemy(app)
exec(open("www/models.py").read())
db.init_app(app)
