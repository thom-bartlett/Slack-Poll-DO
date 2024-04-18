from flask import Flask, request
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
import os
import json
import logging
from num2words import num2words
from pymongo import MongoClient
from slack_sdk.errors import SlackApiError
from pathlib import Path

app = App(process_before_response=True)
logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

dbpass = os.environ.get("DB_PASS")
mongoClient = MongoClient(
    'mongodb+srv://slack-poll-f9932d0b.mongo.ondigitalocean.com',
    username='dotest',
    password=dbpass,
    tls=True)
db = mongoClient.admin.Poll

def get_CreationView():
    p = Path(__file__).with_name('creationView.json')
    with p.open('r') as f:
        view = json.loads(f.read())
    return view

# Slack Shortcut activated - send modal view
@app.shortcut("poll")
def open_modal(ack, shortcut, client):
    """Send creation poll creation modal"""
    ack()
    creation_View = get_CreationView()
    client.views_open(
        trigger_id=shortcut["trigger_id"],
        view=creation_View
    )

# Another option was added to poll creation view - update and respond
@app.action("add-option-action")
def update_modal(ack, body, client):
    """Add new question to poll creation view. Triggered by button."""
    ack()
    # logging
    body_json = json.dumps(body)
    logger.info(body_json)
    # determine current length and where to add new survey question
    view_Length = len(body["view"]["blocks"])
    insert_Index = view_Length - 2
    new_Option = (view_Length - 4)
    # build new survey question
    type_Blocks = {
			"block_id": f"option-{new_Option}",
			"type": "input",
			"element": {
				"type": "plain_text_input",
				"action_id": "plain_text_input-action"
			},
			"label": {
				"type": "plain_text",
				"text": f"Option {new_Option}",
				"emoji": True
			}
		}
    # get existing questions and insert new question
    new_Blocks = body["view"]["blocks"]
    new_Blocks.insert(insert_Index, type_Blocks)
    new_View = get_CreationView()
    new_View["blocks"] = new_Blocks
    new_View_json = json.dumps(new_View)
    logger.info(new_View_json)
    # send the update
    client.views_update(
        view_id = body["view"]["id"],
        hash = body["view"]["hash"],
        view = new_View_json
    )

@app.action("save")
def savePoll(ack, body, client):
    ack()
    # logging
    body_json = json.dumps(body)
    logger.info(body_json)

@app.action("view-saved")
def viewSaved(ack, body, client):
    ack()
    # logging
    body_json = json.dumps(body)
    logger.info(body_json)

def get_Channels(client, current_channel):
    """check if bot has permission to post in a channel"""
    try:
        client.conversations_info(
            channel=current_channel
        )
        logger.info("In Channel")
        return True
    except:
        logger.info("Not in Channel")
        return False

def build_Poll(question, votes_Allowed, visibility, state_values, submitter):
    """Take poll input and create message in blocks format for slack channel"""
    title_block=[
        {
            "type": "section",
            "block_id": "question",
            "text": {
                "type": "mrkdwn",
                "text": f"*{question}*",
            }
        }
    ]
    anonymous_block = [
        {
			"type": "context",
			"elements": [
				{
					"type": "plain_text",
					"text": ":bust_in_silhouette: This poll is anoymous. The identity of all respondents will be hidden",
					"emoji": True
				}
			]
		},
    ]
    options_block = [
        {
			"type": "context",
			"elements": [
				{
					"type": "plain_text",
					"text": votes_Allowed,
					"emoji": True
				}
			]
		},
    ]
    index = 1
    text_Values = {}
    blocks = []
    if visibility:
        blocks = blocks + anonymous_block + title_block + options_block
    else:
        blocks = blocks + title_block + options_block
    for key, value in state_values.items():
        if "option" not in key:
            pass
        else:
            written_Number = num2words(index)
            option = value["plain_text_input-action"]["value"]
            block_id = key
            question_Builder = [
                {
                    "type": "section",
                    "block_id": block_id,
                    "text": {
                        "type": "mrkdwn",
                        "text": f":{written_Number}: {option}",
                    },
                    "accessory": {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": f":{written_Number}:",
                            "emoji": True
                        },
                        "value": f"{block_id}",
                        "action_id": "vote"
                    }
                }]
            index +=1
            text_Values.update({block_id: f":{written_Number}: {option}"})
            blocks = blocks + question_Builder
    final_block = [{
			"type": "context",
			"elements": [
				{
					"type": "mrkdwn",
					"text": f"Created by <@{submitter}> with VentureWell Poll"
				}
			]
		}]
    blocks = blocks + final_block
    blocks = json.dumps(blocks)
    logger.info(f"Final message blocks to be sent to channel: {blocks}")
    return blocks, text_Values

def send_Message(client, channel, ack, blocks):
    """Send formatted message to desired channel"""
    # check if bot can post to channel
    in_Channel = get_Channels(client, channel)
    # if not in channel send error ack
    if not in_Channel:
        ack(
            response_action="errors",
            errors={
                "channel": "The Polling app is not a part of this private channel so it can't send the poll. Please add it."
            }
        )
        return False, "Not in Channel"
    # if in channel send normal ack
    else:
        ack()   
        # Post message
        try:
            result = client.chat_postMessage(
                channel=channel, 
                blocks=blocks
            )
            time = result["message"]["ts"]
            logger.info(f"Try result = {result}")
            return True, time
        except SlackApiError as e:
            logger.info(e)
            logger.info("Bot not in channel")
            return False, e

# Accept the submitted poll
@app.view("poll_view")
def handle_Poll_Submission(ack, body, logger, client):
    """Accept submitted poll and kick off poll building"""
    # collect values
    state_values = body["view"]["state"]["values"]
    channel = state_values["channel"]["channel"]["selected_conversation"]
    question = state_values["question"]["plain_text_input-action"]["value"]
    votes_Allowed = state_values["votes-allowed"]["votes-allowed-action"]["selected_option"]["text"]["text"]
    visibility = state_values["visibility"]["visibility-action"]["selected_options"]
    submitter = body["user"]["id"]
    # build Poll
    blocks, text_Values = build_Poll(question, votes_Allowed, visibility, state_values, submitter)
    # send message
    status, time = send_Message(client, channel, ack, blocks)
    if status:
        db[time].insert_one(text_Values)
        db[time].insert_one({"anonymous": visibility})
        db[time].insert_one({"votes_allowed": votes_Allowed})
    else:
        logger.exception(f"Failed to send message to channel. Error message {time}")

def store_Vote(body):
    """Update database with new vote"""
    logger.info("storing vote")
    time = body["message"]["ts"]
    voter = body["user"]["id"]
    vote = body["actions"][0]["value"]
    document = db[time].find_one({"id": voter})
    votes_allowed = db[time].find_one({"votes_allowed": "Select multiple options"})
    # Check if user previously voted
    if document:
        # Check more specifically if they voted for the same thing
        specific_document = db[time].find_one({"id": voter, "vote": vote})
        # If they are voting for the same thing as previously just delete
        if specific_document:
            db[time].delete_one({"id": voter, "vote": vote})
        elif votes_allowed:
            db[time].insert_one({"id": voter, "vote": vote})
        # if they are voting for something different delete and add
        else:
            db[time].delete_one({"id": voter})
            db[time].insert_one({"id": voter, "vote": vote})
    # if they didn't vote add their vote
    else:
        db[time].insert_one({"id": voter, "vote": vote})

# when databse is migrated hopefully we can split this up a bit
def retrieve_Vote(body):
    """Retrieve votes from DB and build message"""
    logger.info("retrieving vote")
    blocks = body["message"]["blocks"]
    ts = body["message"]["ts"]
    document = db[ts].find({})
    channel = body["channel"]["id"]
    # check if anonymous - shouldn't there be any easier way to query the db?
    for i in document:
        if "anonymous" in i:
            anonymous = i["anonymous"]
    # rebuild message for Slack channel
    for block in blocks:
        # skip first section which doesn't change
        if "option" not in block["block_id"]:
            pass
        else:
            count_Cursor = db[ts].find({"vote": block["block_id"]})
            # need to pull this from DB again for some reason
            document = db[ts].find({})
            count = len(list(count_Cursor))
            text = document[0][block["block_id"]]
            logger.info(block)
            user_list = []
            user_list_Pretty = []
            if not anonymous:
                # logic to grab all users who voted
                for i in document:
                    if "id" in i:
                        if i["vote"] == block["block_id"]:
                            user = i["id"]
                            user_list.append(f"<@{user}>")
                            user_list_Pretty = ", ".join(user_list)
                # check if list is empty so it doesn't post empty list []
                if user_list_Pretty:
                    block["text"].update({"text": f"{text}\n`{count}` {user_list_Pretty}"})
                else:
                    block["text"].update({"text": f"{text}\n`{count}`"})
            else:
                block["text"].update({"text": f"{text}\n`{count}`"})
    return channel, ts, blocks

def update_Poll(channel, ts, blocks):
    """Send update poll blocks back to channel"""
    try:
        app.client.chat_update(channel=channel, ts=ts, blocks=blocks)
        logger.info("action item updated")
    except Exception as e:
        logger.exception(f"Failed to update message error: {e}")


# receive a vote and do the needful
@app.action("vote")
def handle_Vote(ack, body, logger):
    """initial vote handler, kicks off processing"""
    ack()
    body_json = json.dumps(body)
    logger.info(body_json)
    store_Vote(body)
    channel, ts, blocks = retrieve_Vote(body)
    update_Poll(channel, ts, blocks)

flask_app = Flask(__name__)
handler = SlackRequestHandler(app)

@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)
