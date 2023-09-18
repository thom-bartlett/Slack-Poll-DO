from flask import Flask, request
from flask import render_template
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler

app = App()

flask_app = Flask(__name__)
handler = SlackRequestHandler(app)

@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)
