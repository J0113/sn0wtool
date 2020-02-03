import wx
import wx.html
import wx.adv
import socket
import paramiko
import os
from threading import Thread
from time import sleep
import json
import logging
import requests
from scp import SCPClient


class sn0wtool(wx.Frame):
    def __init__(self, parent, title):
        wx.Frame.__init__(
            self,
            parent,
            -1,
            title,
            size=(500, 400)
        )
        self.html = wx.html.HtmlWindow(self)
        self.html.Bind(wx.html.EVT_HTML_LINK_CLICKED, self.onURL)

        self.first_run()

        self.actions = []
        self.update_actions()

        # styling is limited: https://www.pythonstudio.us/wxpython/how-can-i-display-html-in-a-wxpython-window.html
        self.open_page("html/nodevice.html", {'actions_count': str(len(self.actions))})

        #
        # Let's setup the ssh brigde (we will be using iproxy since that is WAY more stable than tcprelay)
        ssh_port = self.get_open_port()
        sshbridge = Thread(target=self.ssh_bridge, args=(ssh_port, 44))
        sshbridge.daemon = True
        sshbridge.start()

        sshdeamon = Thread(target=self.ssh_deamon, args=(ssh_port,))
        sshdeamon.start()

    def onURL(self, evt):
        link = evt.GetLinkInfo()
        href = link.GetHref()
        if href == "exit":
            exit()
        if href.startswith('action='):
            the_id = int(href.replace("action=", "", 1))
            action = self.get_action_by_id(the_id)
            msg = wx.MessageDialog(None, action["description"],
                                   f'Are you sure you want to run {action["name"]} (by {action["author"]})?',
                                   wx.YES_NO | wx.ICON_WARNING)
            result = msg.ShowModal() == wx.ID_YES
            msg.Destroy()
            if result:
                print("running: " + action["name"])
                # self.run_action(the_id)
                run_action_thread = Thread(target=self.run_action, args=(the_id,))
                run_action_thread.start()
        elif href.startswith('revert='):
            the_id = int(href.replace("revert=", "", 1))
            action = self.get_action_by_id(the_id)
            msg = wx.MessageDialog(None,
                                   "The author has created a revert script, this does not guarantee compleet revertion.",
                                   f'Are you sure you want to run the revert of {action["name"]} (by {action["author"]})?',
                                   wx.YES_NO | wx.ICON_WARNING)
            result = msg.ShowModal() == wx.ID_YES
            msg.Destroy()
            if result:
                print("reverting: " + action["name"])
                # self.run_action(the_id, True)
                run_action_thread = Thread(target=self.run_action, args=(the_id, True))
                run_action_thread.start()
        elif href.startswith('readdescription='):
            the_id = int(href.replace("readdescription=", "", 1))
            action = self.get_action_by_id(the_id)
            msg = wx.MessageDialog(None, action["description"],
                                   f'{action["name"]} by {action["author"]}', wx.OK | wx.ICON_INFORMATION)
            msg.ShowModal()
            msg.Destroy()
        elif href == "update_actions":
            self.update_actions(True, True)
        else:
            self.open_page(href)

    def open_page(self, name, replacements=None):
        file = open(name, "r").read()
        if replacements:
            for replace, replacement in replacements.items():
                file = file.replace("{{" + replace + "}}", replacement)
        wx.CallAfter(self.html.SetPage, file)

    def first_run(self):
        if not os.path.exists("html"):
            os.makedirs("html")
        if not os.path.exists("nodevice.html"):
            with open("html/nodevice.html", 'wb') as f:
                f.write(requests.get("https://raw.githubusercontent.com/J0113/sn0wtool/master/html/nodevice.html").content)
        if not os.path.exists("device.html"):
            with open("html/device.html", 'wb') as f:
                f.write(requests.get("https://raw.githubusercontent.com/J0113/sn0wtool/master/html/device.html").content)
        pass

    def update_actions(self, online_update=False, online_sources=False):

        # Online Part
        if online_update or not os.path.exists("actions"):
            if online_sources or not os.path.exists("sources.json"):
                with open("sources.json", 'wb') as f:
                    f.write(requests.get("http://raw.githubusercontent.com/J0113/sn0wtool/master/sources.json").content)
            if not os.path.exists("actions"):
                os.makedirs("actions")
            else:
                for file in os.listdir("actions"):
                    if os.path.splitext(file)[1] == ".json":
                        os.unlink("actions/" + file)
            if os.path.exists("sources.json"):
                for source in json.load(open("sources.json", "r")):
                    filename = "".join(x for x in source if x.isalnum())
                    try:
                        with open("actions/" + filename + ".json", 'wb') as f:
                            f.write(requests.get(source).content)
                    except:
                        pass

        # Loading in the Actions
        self.actions = []
        if os.path.exists("actions"):
            for file in os.listdir("actions"):
                if os.path.splitext(file)[1] == ".json":
                    try:
                        self.actions = self.actions + json.load(open("actions/" + file, "r"))
                    except:
                        pass
        print(str(len(self.actions)) + " actions loaded")
        self.open_page("html/nodevice.html", {'actions_count': str(len(self.actions))})
        pass

    def ssh_bridge(self, port, devicetcp=44):
        os.system(f"iproxy {str(port)} {str(devicetcp)}")

    def ssh_deamon(self, port):
        while AppRunning:
            self.ssh = self.create_ssh_connection(port)
            while AppRunning and not self.ssh:
                sleep(1)  # No connection yet, lets try and make one
                self.ssh = self.create_ssh_connection(port)
            if not AppRunning:
                break
            device_name = self.ssh_exec("scutil --get ComputerName")
            print(f"Connected to device ({device_name}) on port {str(port)}")
            self.open_page("html/device.html",
                           {'device_name': device_name, 'port': str(port), 'actions_table': self.create_actions_html()})

            while AppRunning and self.ssh_connection_is_alive():
                sleep(2)  # The connection is still running
                pass
            print("Device disconnected")
            self.open_page("html/nodevice.html", {'actions_count': str(len(self.actions))})

    def create_ssh_connection(self, port, username="root", password="alpine"):
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        logging.getLogger("paramiko").setLevel(logging.CRITICAL)

        try:
            ssh.connect("localhost", port=port, username=username, password=password, look_for_keys=False)
            return ssh
        except Exception as e:
            return False

    def get_open_port(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("", 0))
        s.listen(1)
        port = s.getsockname()[1]
        s.close()
        return port

    def read_stdout(self, stdout, rmv_nl=False):
        the_return = stdout.read().decode("utf-8")
        if rmv_nl:
            return the_return.rstrip()
        return the_return

    def ssh_connection_is_alive(self):
        try:
            self.ssh.exec_command('echo " "', timeout=5)
        except Exception:
            return False
        return True

    def ssh_exec(self, command):
        ssh_stdin, ssh_stdout, ssh_stderr = self.ssh.exec_command(command)
        if ssh_stderr:
            print(self.read_stdout(ssh_stderr, True))
        return self.read_stdout(ssh_stdout, True)

    def create_actions_html(self):
        html = '<table>'
        html += '<tr><th>Name</th><th>Description</th><th>Author</th><th>Run</th><th>Revert</th></tr>'
        i = 0
        for action in self.actions:
            html += f'<tr><td>{action["name"]}</td><td>{action["description"][:45]}{self.read_description_btn(i)}</td><td>{action["author"]}</td><td><a href="action={i}">Run</a></td><td>{self.revert_btn(i)}</td></tr>'
            i = i + 1
        html += '</table>'
        return html

    def get_action_by_id(self, action_id):
        if not isinstance(action_id, int):
            action_id = int(action_id)
        return self.actions[action_id]

    def read_description_btn(self, id):
        description = self.get_action_by_id(id)["description"]
        if len(description) > 45:
            return f" <a href='readdescription={id}'>...</a>"
        return ""

    def revert_btn(self, id_action):
        action = self.get_action_by_id(id_action)
        if "revert" in action:
            return f" <a href='revert={id_action}'>Revert</a>"
        return "-"

    def run_action(self, id_action, revert=False):
        action = self.get_action_by_id(id_action)
        script = action["revert"] if revert else action["actions"]
        for the_action in script:
            # Shell commands:
            if the_action["type"] == "command":
                print(self.ssh_exec(the_action["command"]))
                pass
            # Show Message
            elif the_action["type"] == "message":
                message = wx.MessageDialog(None, "", the_action["message"], wx.OK | wx.ICON_INFORMATION)
                message.ShowModal()
                message.Destroy()
                pass
            # Get File (from connection to pc)
            elif the_action["type"] == "getfile":
                with SCPClient(self.ssh.get_transport()) as scp:
                    scp.get(the_action["location"], the_action["destination"])
                pass
            # Get File (from internet to pc)
            elif the_action["type"] == "getonlinefile":
                if os.path.exists(the_action["destination"]) and "cache" in the_action and the_action["cache"]:
                    print("Using Cached File")
                else:
                    with open(the_action["destination"], 'wb') as f:
                        f.write(requests.get(the_action["location"]).content)
                    pass
                pass
            # Put File (from pc to connection)
            elif the_action["type"] == "putfile":
                with SCPClient(self.ssh.get_transport()) as scp:
                    scp.put(the_action["location"], the_action["destination"])
                pass
            else:
                print("Unsupported Action:" + the_action["type"])
        msg = wx.MessageDialog(None, "",
                               f'{"Revert of " + action["name"] if revert else action["name"]} was completed.',
                               wx.OK | wx.ICON_INFORMATION)
        msg.ShowModal()
        msg.Destroy()


AppRunning = True
app = wx.App()
frm = sn0wtool(None, "sn0wtool")
frm.Show()
app.MainLoop()
AppRunning = False
exit()
