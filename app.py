from flask import Flask, request
from flask import render_template
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
import os
import json
import logging
from num2words import num2words
from pymongo import MongoClient
from slack_sdk.errors import SlackApiError
import copy

logging.basicConfig(level=logging.DEBUG)

app = App(process_before_response=True)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

creation_View = {
	"callback_id": "poll_view",
	"type": "modal",
	"title": {
		"type": "plain_text",
		"text": "VentureWell App",
		"emoji": True
	},
	"submit": {
		"type": "plain_text",
		"text": "Submit",
		"emoji": True
	},
	"close": {
		"type": "plain_text",
		"text": "Cancel",
		"emoji": True
	},
	"blocks": [
		{
			"type": "section",
			"text": {
				"type": "mrkdwn",
				"text": "*Select a channel to post the survey in:*"
			},
			"accessory": {
				"type": "conversations_select",
				"placeholder": {
					"type": "plain_text",
					"text": "Select a conversation",
					"emoji": True
				},
				"default_to_current_conversation": True,
				"action_id": "channel"
			}
		},
		{
			"block_id": "question",
			"type": "input",
			"element": {
				"type": "plain_text_input",
				"action_id": "plain_text_input-action"
			},
			"label": {
				"type": "plain_text",
				"text": "Question or Topic:",
				"emoji": True
			}
		},
		{
			"block_id": "votes-allowed",
			"type": "input",
			"element": {
				"type": "static_select",
				"placeholder": {
					"type": "plain_text",
					"text": "Select an item",
					"emoji": True
				},
				"options": [
					{
						"text": {
							"type": "plain_text",
							"text": "Select multiple options",
							"emoji": True
						},
						"value": "one-vote"
					},
					{
						"text": {
							"type": "plain_text",
							"text": "Select one option",
							"emoji": True
						},
						"value": "multiple-votes"
					}
				],
				"action_id": "votes-allowed-action"
			},
			"label": {
				"type": "plain_text",
				"text": "How do you want people to respond?",
				"emoji": True
			}
		},
		{
			"block_id": "option-1",
			"type": "input",
			"element": {
				"type": "plain_text_input",
				"action_id": "plain_text_input-action"
			},
			"label": {
				"type": "plain_text",
				"text": "Option 1",
				"emoji": True
			}
		},
		{
			"block_id": "option-2",
			"type": "input",
			"optional": True,
			"element": {
				"type": "plain_text_input",
				"action_id": "plain_text_input-action"
			},
			"label": {
				"type": "plain_text",
				"text": "Option 2",
				"emoji": True
			}
		},
		{
			"block_id": "add-option",
			"type": "actions",
			"elements": [
				{
					"type": "button",
					"text": {
						"type": "plain_text",
						"text": "Add another option",
						"emoji": True
					},
					"value": "add-option-button",
					"action_id": "add-option-action"
				}
			]
		},
		{
			"block_id": "visibility",
			"type": "section",
			"text": {
				"type": "mrkdwn",
				"text": "*Settings*"
			},
			"accessory": {
				"type": "checkboxes",
				"options": [
					{
						"text": {
							"type": "mrkdwn",
							"text": "Make responses anonymous"
						},
						"value": "visibility-value"
					}
				],
				"action_id": "visibility-action"
			}
		}
	]
}

# Slack Shortcut activated - send modal view
@app.shortcut("poll")
def open_modal(ack, shortcut, client):
    # Acknowledge the shortcut request
    ack()
    # Send initial view
    client.views_open(
        trigger_id=shortcut["trigger_id"],
        view=creation_View
    )

@app.error
def custom_error_handler(error, body, logger):
    logger.exception(f"Error: {error}")
    logger.info(f"Request body: {body}")
    
@app.action("visibility-action")
def handle_visibility(ack, body, logger):
    ack()
    logger.info(body)

@app.action("channel")
def handle_visibility(ack, body, logger):
    ack()
    logger.info(body)

# Another option was added to poll creation view - update and respond
@app.action("add-option-action")
def update_modal(ack, body, client):
    ack()
    body_json = json.dumps(body)
    logger.info(body_json)
    view_Length = len(body["view"]["blocks"])
    insert_Index = view_Length - 2
    new_Option = (view_Length - 4)
    type_Blocks ={
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
    new_Blocks = body["view"]["blocks"]
    new_Blocks.insert(insert_Index, type_Blocks)
    new_View = copy.deepcopy(creation_View)
    new_View["blocks"] = new_Blocks
    new_View_json = json.dumps(new_View)
    logger.info(new_View_json)
    client.views_update(
        view_id = body["view"]["id"],
        hash = body["view"]["hash"],
        view = new_View_json
    )

# Accept the submitted poll and convert to a Slack block format
@app.view("poll_view")
def handle_view_events(ack, body, logger, client):
    dbpass = os.environ.get("DB_PASS")
    mongoclient = MongoClient(f"mongodb+srv://unfo33:{dbpass}@cluster0.deaag.mongodb.net/?retryWrites=true&w=majority")
    body_json = json.dumps(body)
    logger.info(body_json)
    ack()
    # collect values
    state_values = body["view"]["state"]["values"]
    channel = state_values["channel"]["channel"]["selected_conversation"]
    question = state_values["question"]["plain_text_input-action"]["value"]
    votes_allowed = state_values["votes-allowed"]["votes-allowed-action"]["selected_option"]["text"]["text"]
    visibility = state_values["visibility"]["visibility-action"]["selected_options"]
    submitter = body["user"]["id"]
    # options = []
    # for key, value in state_values.items():
    #     if "option" in key:
    #         options.append(value)
    # craft message
    blocks = []
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
					"text": votes_allowed,
					"emoji": True
				}
			]
		},
    ]
    index = 1
    text_Values = {}
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
    logger.info(f"Finaly message blocks to be sent to channel: {blocks}")
    db = mongoclient.Poll
    try:
        result = client.chat_postMessage(
            channel=channel, 
            blocks=blocks
        )
        time = result["message"]["ts"]
        time = result["message"]["ts"]
        db[time].insert_one(text_Values)
        db[time].insert_one({"anonymous": visibility})
        db[time].insert_one({"votes_allowed": votes_allowed})
        return time
    except SlackApiError as e:
        logger.exception(f"Error posting message error: {e}")

def store_Vote(body, client):
    logger.info("storing vote")
    db=client.Poll
    ts = body["message"]["ts"]
    voter = body["user"]["id"]
    vote = body["actions"][0]["value"]
    document = db[ts].find_one({"id": voter})
    votes_allowed = db[ts].find_one({"votes_allowed": "Select multiple options"})
    # Check if user previously voted
    if document:
        # Check more specifically if they voted for the same thing
        specific_document = db[ts].find_one({"id": voter, "vote": vote})
        # If they are voting for the same thing as previously just delete
        if specific_document:
            db[ts].delete_one({"id": voter, "vote": vote})
        elif votes_allowed:
            db[ts].insert_one({"id": voter, "vote": vote})
        # if they are voting for something different delete and add
        else:
            db[ts].delete_one({"id": voter})
            db[ts].insert_one({"id": voter, "vote": vote})
    else:
        db[ts].insert_one({"id": voter, "vote": vote})

def retrieve_Vote(client, body):
    logger.info("retrieving vote")
    db=client.Poll
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
    try:
        app.client.chat_update(channel=channel, ts=ts, blocks=blocks)
        logger.info("action item updated")
    except Exception as e:
        logger.exception(f"Failed to update message error: {e}")


# receive a vote and do the needful
@app.action("vote")
def handle_some_action(ack, body, logger):
    ack()
    body_json = json.dumps(body)
    logger.info(body_json)
    dbpass = os.environ.get("DB_PASS")
    client = MongoClient(f"mongodb+srv://unfo33:{dbpass}@cluster0.deaag.mongodb.net/?retryWrites=true&w=majority")
    store_Vote(body, client)
    retrieve_Vote(client, body)

flask_app = Flask(__name__)
handler = SlackRequestHandler(app)

@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)
