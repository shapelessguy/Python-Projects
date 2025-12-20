from abc import ABC, abstractmethod
from wg import bac
from datetime import datetime
from announcements_cb import *


class Function(ABC):
    description = """"""
    arguments = {}
    examples = []

    def __init__(self):
        pass

    @abstractmethod
    def action(self):
        pass


class SendPing(Function):
    description = """
        Send a ping to the chatbot to check if it is still alive.
    """
    arguments = {
    }
    examples = [
        ['send a ping', {}],
        ['can you check if you are alive?', {}],
        ['ping pls', {}],
    ]

    def action(self, message):
        message.data = {'action': actions['ping']}
        ping_handler1(message, continue_chain=False)


wg_activities = [x.name for x in bac.Activities().get_regular()]
    


class SendPraise(Function):
    description = """
        Send a praise (a telegram message of appreciation) to the member of the WG which was assigned to the mentioned activity.
        A nice comment will accompany the message as well.
    """
    arguments = {
        "activity": f"One of the following {len(wg_activities)} activities ({', '.join(wg_activities)})",
        "comment": "A required comment regarding the praise",
    }
    examples = [
        ['Bathroom did a great job last week', 'Should I praise the responsible then?'],
        ['It s good that management things are done properly', {'activity': 'Management', 'comment': 'Good overall job!'}],
        ['Tell Arman he did a good job at cleaning the bathtub', 'I am not sure, what activity was Arman on? Bathrooms?'],
        ['Praise Floor', 'Please provide a comment for this praise.'],
    ]

    def action(self, message, **kwargs):
        message.data = {'action': actions['praise']}
        blame_handler1(message, continue_chain=False)
        message.text = kwargs['activity']
        if praise_handler1(message, continue_chain=False) is False:
            return
        message.text = kwargs['comment']
        message_handler(message, continue_chain=False)


class SendBlame(Function):
    description = """
        Send a blame (a telegram message of disappointment) to the member of the WG which was assigned to the mentioned activity.
        The blame will be recorded in the system and if the subject obtains at least 2 blames in one week, they must redo the activity in the future.
    """
    arguments = {
        "activity": f"One of the following {len(wg_activities)} activities ({', '.join(wg_activities)})"
    }
    examples = [
        ['send a blame to Kitchen because it is very dirty', {'activity': 'Kitchen'}],
        ['Blame Kitchen now!', {'activity': 'Kitchen'}],
        ['The cleaning of Floor has been terrible!', 'Would you like to blame Floor?'],
        ['execute blame for bathrooms because toilets are shit', {'activity': 'Bathrooms'}],
        ['execute blame for Mara', 'Please provide the name of the activity rather than the name of the responsible..'],
    ]

    def action(self, message, **kwargs):
        message.data = {'action': actions['blame']}
        blame_handler1(message, continue_chain=False)
        message.text = kwargs['activity']
        blame_handler2(message, continue_chain=False)


class Swap(Function):
    description = """
        Swap the activity of a given wg member with the activity of another member. The user must indicate what activity they wants to swap their
        activity with and in what date (which must be a Monday in the future with respect to the current date).
    """
    arguments = {
        "activity": f"One of the following {len(wg_activities)} activities ({', '.join(wg_activities)})",
        "date_str": "When the swap has to happen in the form of YYYY-MM-DD",
    }
    examples = [
        ['I want to exchange my task with Mara', "Please provide Mara's activity and the date (remember the date must be referred to a Monday)."],
        ['Swap my task with Management on January', "January doesn't mean anything. The date must be the Monday referred to the week of the swap."],
        ['Swap my task with Floor on the 17th of February 25', {'activity': 'Bathrooms', 'date_str': "2025-02-17"}],
    ]

    def action(self, message, **kwargs):
        message.data = {'action': actions['swap']}
        swap_handler1(message, continue_chain=False)
        message.text = kwargs['activity']
        swap_handler2(message, continue_chain=False)
        temp_data[message.chat.id]['calendar_result'] = datetime.strptime(kwargs['date_str'], "%Y-%m-%d")
        swap_handler3(message, continue_chain=False)


class ShowVacations(Function):
    description = """
        Show the vacations booked by a member of the WG.
    """
    arguments = {}
    examples = [
        ['What are my vacations?', {}],
        ['What are the vacations of Mara', "I have no idea, you could check it by yourself."],
        ['Show all of my vacations on January', 'If you want I can show your next booked vacations..'],
    ]

    def action(self, message, **kwargs):
        message.data = {'action': actions['vacations']}
        vacations_handler1(message, continue_chain=False)


class BookVacation(Function):
    description = """
    Book a vacation in the indicated day (which must be a Monday in the future with respect to the current date).
    The mentioned Monday is identified as the start of the week of vacation.
    The subject is not forced to do any activity during the week they marked as vacation.
    """
    arguments = {
        "date_str": "Date of the vacation in the form of YYYY-MM-DD"
    }
    examples = [
        ['I want take vacation next week', "Then tell me the date (remember the date must be referred to a Monday)."],
        ['I want to book vacations for the 17th of February 25', {'date_str': "2025-02-17"}],
    ]

    def action(self, message, **kwargs):
        message.data = {'action': actions['book']}
        vacation_handler1(message, continue_chain=False)
        temp_data[message.chat.id]['calendar_result'] = datetime.strptime(kwargs['date_str'], "%Y-%m-%d")
        if vacation_handler2(message, continue_chain=False) is False:
            new_request(message, "❌ This vacation has already been booked.", False)


class UnbookVacation(Function):
    description = """
    Unbook a vacation in the indicated day (which must be a Monday in the future with respect to the current date).
    The mentioned Monday is identified as the start of the week of vacation.
    The subject will be subject to an automatically generated activity during the week they marked as non-vacation.
    """
    arguments = {
        "date_str": "Date of the vacation in the form of YYYY-MM-DD"
    }
    examples = [
        ['I want to unbook vacation next week', "Then tell me the date (remember the date must be referred to a Monday)."],
        ["Jokin, I don't want to take any vacation on the 17th of February 25", {'date_str': "2025-02-17"}],
    ]

    def action(self, message, **kwargs):
        message.data = {'action': actions['book']}
        vacation_handler1(message, continue_chain=False)
        temp_data[message.chat.id]['calendar_result'] = datetime.strptime(kwargs['date_str'], "%Y-%m-%d")
        if vacation_handler2(message, continue_chain=False, unbook_only=True) is False:
            message.text = "YES"
            vacation_handler3(message, continue_chain=False)


class CreateExpense(Function):
    description = """
    Create an expense that will be later reimbursed by the WG master. An expense has a price and it is accompanied by a comment which
    indicates what item has been bought by the wg member.
    """
    arguments = {
        "price_str": "Price of the bougth item (or items) as a single float",
        "comment": "A required comment regarding the expense",
    }
    examples = [
        ['I bought plants and chocolate', "Ok, let's do one expense at a time, shall we?"],
        ['I bought plants yesterday', "How much did you pay?"],
        ['I payed 17 euro for the wg', "What did you buy with that money?"],
        ['I payed 4.5 euro for the flowers', {"price_str": "4.50", "comment": "flowers"}],
    ]

    def action(self, message, **kwargs):
        message.data = {'action': actions['expense']}
        expense_handler1(message, continue_chain=False)
        message.text = kwargs['price_str']
        expense_handler2(message, continue_chain=False)
        message.text = kwargs['comment']
        expense_handler3(message, continue_chain=False)
