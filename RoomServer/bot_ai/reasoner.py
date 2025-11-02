import os
import json
bot_ai_path = os.path.dirname(__file__)
with open(os.path.join(bot_ai_path, 'genai.json'), 'r') as file:
    genai_token = json.load(file)['token']
import google.generativeai as genai
genai.configure(api_key=genai_token)
model = genai.GenerativeModel("gemini-2.0-flash")


def reason(message, bh, functions, history, md):
    print('reasoning..')
    bh.send_msg(message.chat.id, "🧠 I am stupid sorry!")
    return False
    result = analyze_message(message, functions, history, md)

    args = [x.replace('[', '') for x in result.split(']') if x not in ['[', ']', '']]
    if args[0] == 'execute':
        function_name = args[1]
        kwargs = {x.split('=')[0]: x.split('=')[1] for x in args[2:]}
        for f in functions:
            if f.__class__.__name__ == function_name:
                f.action(message, **kwargs)
                return True
    else:
        bh.send_msg(message.chat.id, "🧠 " + result)
        return False


def analyze_message(message, functions, history, md):
    """
    Analyze the incoming message and return a simple string in case the command needs to be further investigated,
    or a string in the format [execute][FUNCTION_NAME][argname1=arg1][argname2=arg2]... .
    """
    try:
        cur_history_ = [{'role': x['role'], 'parts': x['message']} for x in history[str(message.chat.id)][-20:]]
        cur_history = []
        for h in cur_history_[::-1]:
            if '✅' not in h['parts'] and '' not in h['parts']:
                cur_history.append(h)
            else:
                break
        cur_history = cur_history[::-1]


        functions_txt = ""
        f_description = {}
        for f in functions:
            description = f.description.replace('\n', ' ').replace('\t', ' ')
            while '  ' in description:
                description = description.replace('  ', ' ')
            f_description[f.__class__.__name__] = description
            functions_txt += f"{f.__class__.__name__}: {description}\n"

        intro = f"""
You are a helpful AI assistant. Always provide clear and concise answers. In particular you are a telegram chatbot that helps out members of a shared flat (WG)
into their weekly activities. Most of them are related to the cleaning of the WG, and other to expenses, vacations etc.
For every request of the user you must recognize whether the request is the continuation of the previous conversation and reply accordingly, or"""
        system_prompt = f"""
{intro} if the current request matches one of the following themes.
{functions_txt}
Based on the descriptions of these themes, you have to report whether one of them needs to be immediately look into. The way you signal this is by replying
with the name of the theme in brackets (ex: [SendPing]). If you don't recognize any theme in the user's request, just reply normally.
If the user just asks for information, just provide them with it.
The cleaning activities in our WG are the following: {', '.join(md['activities'])}. People in our WG are: {', '.join(md['wg_members'].values())}.
Remember it is extrimely important that if you recognize a theme, you just reply with the name of the theme [THEME_NAME], therefore the user will know if you
are able to recognize important topics of the conversation. The final message should only contain the name of the theme and ANGULAR BRACKETS.
        """
        chat = model.start_chat(history=[{'role': 'user', 'parts': system_prompt}] + cur_history)
        response = chat.send_message(message.text.strip(), stream=False, generation_config={"max_output_tokens": 100}).text
        response = response.replace("🧠", "").strip()
        for f in functions:
            fname = f.__class__.__name__
            if response.replace('[', '[').replace(']', ']') == f"[{fname}]":
                args_str = '\n'.join(['- ' + name + ': ' + descr for name, descr in f.arguments.items()])
                examples = ""
                for qa in f.examples:
                    arg_values = ''.join(['['+an+'='+av+']' for an, av in qa[1].items()]) if type(qa[1]) is dict else qa[1]
                    root_cmd = f"[execute][{fname}]" if type(qa[1]) is dict else ""
                    examples += f"if the user requests \"{qa[0]}\", you reply \"{root_cmd}{arg_values}\";\n"
                system_prompt = f"""
{intro} if there is enough information in the request to call the function {fname}.
The function {fname} has this description: {f_description[fname]}. This function also requires the following arguments:
{args_str}
If there are not enough arguments for the functions, you just prompt the user for the missing information! There is nothing worse than returning a function with
missing or incorrect arguments!
Now that you know how to use the function, the resulted formulation must be given in the following format:
[execute][{fname}]{''.join(['[' + n + '=??]' for n in f.arguments])}{', where the ?? must be replaced by the actual values in the request' if len(f.arguments) > 0 else ''}.
Remember it is extrimely important that if you recognize the arguments, you just reply with that specific format.
In order to fill the arguments you might track back in the discussion trying to find the missing argument.
For instance if the conversation goes "User: I bought a tape", "Assistant: "How much did you pay?", "User: 7 euro", then you know that the user bought tape for 7 euro.
Remember that your answer will be passed to a function, therefore either you reply with all the necessary arguments in the right format, or you prompt for more explainations.
For instance an answer like "[execute][CreateExpense]How much did you pay?" is not acceptable, but "[execute][CreateExpense][price_str=1.50][comment=plants]" or "How much did you pay?" are.
Remember, ONLY ONE MESSAGE, NOTHING MORE.
For instance:
{examples}

Next there is our previous conversation. Your answers are marked byt the '🧠' symbol. NEVER REPEAT YOURSELF.
                """
                chat = model.start_chat(history=[{'role': 'user', 'parts': system_prompt}] + cur_history)
                response2 = chat.send_message(message.text.strip(), stream=False, generation_config={"max_output_tokens": 100}).text.strip()
                response2 = response2.replace("🧠", "").replace('[/execute]', '').strip()
                print(response2)
                return response2
        return response
    except Exception:
        import traceback
        print(traceback.format_exc())
        return "❌ Did you just speak in Martian? Say again."
