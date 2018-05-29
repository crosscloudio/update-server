import datetime

from update_server import db


class UpdateRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    platform = db.Column(db.String(15))
    channel = db.Column(db.String(20))
    version = db.Column(db.String(10))
    query_time = db.Column(db.DateTime(), default=datetime.datetime.utcnow)
    ip = db.Column(db.String())

    # this is a uuid
    install_id = db.Column(db.String(36))

    __table_args__ = (db.Index('update_idx', 'install_id', 'query_time'),
                      db.Index('date_idx', 'query_time'),)
