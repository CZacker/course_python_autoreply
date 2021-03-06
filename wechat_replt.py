# coding=utf8
# 使用前需关注小冰公众号


from __future__ import print_function
from threading import Timer
import itchat
import datetime
from itchat.content import *
from collections import deque

# ---------------------------------------------- config setting ------------------------------------------------------


WAKEN_MSG = [u"在？", u"在吗"]
HIBERNATE_MSG = [u"滚", u"你滚", u"你闭嘴", u"下去吧"]
MAN_MSG = [u"颜值", u"我好看吗？"]
MAN_REPLY = [u"100分！", u"废话，好看呀！"]

TRIGGER_MSG = WAKEN_MSG + HIBERNATE_MSG + MAN_MSG

XIAOBING_IDLENESS_THRESHOLD = 1  # sec
MSG_PROCESS_FREQ = 0.5  # sec


# --------------------------------------------- Handle Friend Chat ---------------------------------------------------


@itchat.msg_register([TEXT, PICTURE], isFriendChat=True)
def text_reply(msg):
    """ handle robot switch and friends messages """
    to_user = itchat.search_friends(userName=msg['ToUserName'])
    from_user = itchat.search_friends(userName=msg['FromUserName'])

    if is_my_outgoing_msg(msg):
        handle_outgoing_msg(msg, to_user)
    else:  # this is an incoming message from my friend
        handle_incoming_msg(msg, from_user)


@itchat.msg_register([TEXT, PICTURE], isGroupChat=True)
def group_reply(msg):
    from_user_name = msg['FromUserName']
    to_user_name = msg['ToUserName']
    if is_my_outgoing_msg(msg):
        group = itchat.search_chatrooms(userName=to_user_name)
        handle_outgoing_msg(msg, group)
    else:
        group = itchat.search_chatrooms(userName=from_user_name)
        handle_incoming_msg(msg, group)


def handle_outgoing_msg(msg, to_user):
    debug_print(u'I sent a message {} to {}'.format(msg['Text'], get_user_display_name(to_user)))
    if msg['Content'] in TRIGGER_MSG:
        handle_robot_switch(msg, to_user)


def handle_incoming_msg(msg, from_user):
    global peer_list

    debug_print(u'I received a message {} from {}'.format(msg['Text'], get_user_display_name(from_user)))
    if msg['Content'] in TRIGGER_MSG:
        handle_robot_switch(msg, from_user)
    else:  # don't ask xiaobing with trigger question
        if msg['FromUserName'] in peer_list:
            handle_message_queue(msg, from_user)


def handle_message_queue(msg, from_user):
    global asker_queue, unprocessed_questions

    from_user_id_name = msg['FromUserName']
    from_user_display_name = get_user_display_name(from_user)
    debug_print(u'Robot reply is on for {}! Adding message to queue...'.format(from_user_display_name))

    if from_user_id_name not in unprocessed_questions:
        # this user has no unprocessed question, adding to the asker queue
        asker_queue.append(from_user_id_name)
    else:
        debug_print(u'{} is asking questions too quickly. Drop the previous one and use the current'.format(
            from_user_display_name
        ))

    # only register the last question of each unprocessed asker
    unprocessed_questions[from_user_id_name] = msg


def handle_robot_switch(incoming_msg, outgoing_msg_target_user):
    """ Turn robot on/off according to the trigger message """
    global peer_list

    if not outgoing_msg_target_user:
        debug_print(u'Outgoing message target user not recognized. Can\'t turn on/off robot')
        return

    display_name = get_user_display_name(outgoing_msg_target_user)
    user_id_name = outgoing_msg_target_user['UserName']

    incoming_msg_content = incoming_msg['Content']
    if incoming_msg_content in WAKEN_MSG:
        if user_id_name not in peer_list:
            debug_print(u'Turning on robot for {}'.format(display_name))
            peer_list.add(user_id_name)
            itchat.send_msg(u'咋了', user_id_name)
        else:
            debug_print(u'Robot is already turned on for {}'.format(display_name))
    elif incoming_msg_content in HIBERNATE_MSG:
        if user_id_name in peer_list:
            debug_print(u'Turning off robot for {}'.format(display_name))
            peer_list.remove(user_id_name)
            itchat.send_msg(u'(默默走开', user_id_name)
        else:
            debug_print(u'Robot is already turned off for {}'.format(display_name))
    elif incoming_msg_content in MAN_MSG:
        if user_id_name not in peer_list:
            debug_print(u'Turning on robot for {}'.format(display_name))
            peer_list.add(user_id_name)
            itchat.send_msg(MAN_REPLY[MAN_MSG.index(incoming_msg_content)], user_id_name)
            peer_list.remove(user_id_name)
        else:
            debug_print(u'Robot is already turned on for {}'.format(display_name))
            itchat.send_msg(MAN_REPLY[MAN_MSG.index(incoming_msg_content)], user_id_name)


# --------------------------------------------- Handle Xiaobing Reply ------------------------------------------------


@itchat.msg_register([TEXT, PICTURE, FRIENDS, CARD, MAP, SHARING, RECORDING, ATTACHMENT, VIDEO], isMpChat=True)
def map_reply(msg):
    """ relay back xiaobing's response """
    if msg['FromUserName'] == xiao_bing_user_name:
        handle_xiaobing_reply(msg)


def handle_xiaobing_reply(msg):
    global current_asker_id_name, last_xiaobing_response_ts, is_xiaobing_busy

    if not current_asker_id_name:
        debug_print('Xiaobing replied but has no one to contact')
        return

    last_xiaobing_response_ts = now()
    is_xiaobing_busy = False
    asker = itchat.search_friends(userName=current_asker_id_name)
    if msg['Type'] == 'Picture':
        debug_print(u'Xiaobing replied a picture. Relaying to {}'.format(get_user_display_name(asker)))
        send_img(msg, current_asker_id_name)
    elif msg['Type'] == 'Text':
        debug_print(u'Xiaobing replied {}. Relaying to {}'.format(msg['Text'], get_user_display_name(asker)))
        itchat.send_msg(u' {}'.format(msg['Text']), current_asker_id_name)
    else:
        # gracefully handle unsupported formats with generic reply
        debug_print(u'Xiaobing replied a {}, which is not yet supported'.format(msg['Type']))
        itchat.send_msg(u'嘤嘤嘤', current_asker_id_name)


# ------------------------------------------ Message Queue Processor ------------------------------------------------


def process_message():
    global asker_queue, current_asker_id_name, last_xiaobing_response_ts, is_xiaobing_busy
    if len(asker_queue) == 0:
        # debug_print(u'Was asked to process message but the queue is empty')
        pass

    elif is_xiaobing_busy:
        # skip this round if xiaobing is currently busy
        pass
    # if no one has asked xiaobing yet or xiaobing has been idle for a period of time
    elif (not last_xiaobing_response_ts or
          now() - last_xiaobing_response_ts > datetime.timedelta(seconds=XIAOBING_IDLENESS_THRESHOLD)):
        current_asker_id_name = asker_queue.popleft()
        msg = unprocessed_questions.pop(current_asker_id_name, None)

        debug_print(u'Xiaobing is available. Asking questions on behalf of {}'.format(
           get_user_display_name(user_id_name=current_asker_id_name)
        ))
        is_xiaobing_busy = True
        ask_xiaobing(msg)

    # check back later
    Timer(MSG_PROCESS_FREQ, process_message).start()


# --------------------------------------------- Helper Functions ---------------------------------------------------


def now():
    return datetime.datetime.now()


def debug_print(msg):
    if not debug:
        return

    try:
        print(u'{} {}'.format(now(), msg))
    except Exception as e:
        print(str(e))


def send_img(msg, user_name):
    """ wrapper around itchat's weird way of image forwarding """
    msg['Text'](msg['FileName'])
    itchat.send_image(msg['FileName'], user_name)


def ask_xiaobing(msg):
    if msg['Type'] == 'Picture':
        send_img(msg, xiao_bing_user_name)
    else:
        text = msg['Text']
        if text and text.startswith(u''):
            # remove dialog prefix when bots talk to each other
            text = text.replace(u'', '')
        itchat.send_msg(text, xiao_bing_user_name)


def get_user_display_name(user=None, user_id_name=None):
    if user:
        return user['RemarkName'] or user['NickName'] or user['Name']
    elif user_id_name:
        return get_user_display_name(user=itchat.search_friends(userName=user_id_name))
    else:
        return 'user not found'


def is_my_outgoing_msg(msg):
    return msg['FromUserName'] == my_user_name


if __name__ == '__main__':
    itchat.auto_login()
    my_user_name = itchat.get_friends(update=True)[0]["UserName"]
    xiao_bing_user_name = itchat.search_mps(name=u'小冰')[0]["UserName"]

    peer_list = set()
    asker_queue = deque()
    unprocessed_questions = {}
    current_asker_id_name = None
    last_xiaobing_response_ts = None
    debug = True
    is_xiaobing_busy = False

    process_message()
    itchat.run()
