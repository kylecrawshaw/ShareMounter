from AppKit import NSTextField, NSMakeRect, NSRect, NSSecureTextField, NSAlert, \
                   NSCriticalAlertStyle, NSView, NSButton, NSSwitchButton

class AlertDialog(object):

    def __init__(self, title, message):
        self.alert = NSAlert.alloc().init()
        self.alert.setTitle_andMessage_(title, message)
        self.button_return = None

    def display(self):
        self.button_return = self.alert.runModal()

class InputDialog(AlertDialog):

    def __init__(self, title, message):
        AlertDialog.__init__(self, title, message)
        self.input = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 200, 24))
        self.alert.setAccessoryView_(self.input)

    def get_input(self):
        return self.input.stringValue()

class SecureInputDialog(InputDialog):

    def __init__(self, title, message):
        InputDialog.__init__(self, title, message)
        self.input = NSSecureTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 200, 24))
        self.alert.setAccessoryView_(self.input)

class ContinueDialog(AlertDialog):

    def __init__(self, title, message):
        AlertDialog.__init__(self, title, message)
        self.alert.addButtonWithTitle_('OK')
        self.alert.addButtonWithTitle_('Cancel')
        self.alert.setAlertStyle_(NSCriticalAlertStyle)

    def should_continue(self):
        return True if self.button_return == 1000 else False

class PasswordDialog(object):

    def __init__(self):
        ''' initializes an alert with custom view containing username and
            password fields with a save to keychain checkbox'''
        # Create an dialog with ok and cancel buttons
        self.alert = NSAlert.alloc().init()
        self.alert.setMessageText_('Please enter your username and password!')
        self.alert.addButtonWithTitle_('Ok')
        self.alert.addButtonWithTitle_('Cancel')

        # create the view for username and password fields
        accessory_view = NSView.alloc().initWithFrame_(NSMakeRect(0, 114, 250, 110))

        # setup username field and label
        self.username_field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 70, 250, 22))
        username_label = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 94, 250, 20))
        username_label.setStringValue_('Username:')
        username_label.setBezeled_(False)
        username_label.setDrawsBackground_(False)
        username_label.setEditable_(False)
        username_label.setSelectable_(False)

        # setup password field and label
        self.password_field = NSSecureTextField.alloc().initWithFrame_(NSMakeRect(0, 24, 250, 22))
        password_label = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 48, 250, 20))
        password_label.setStringValue_('Password:')
        password_label.setBezeled_(False)
        password_label.setDrawsBackground_(False)
        password_label.setEditable_(False)
        password_label.setSelectable_(False)

        # setup keychain checkbox and label
        self.keychain_checkbox = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, 200, 20))
        self.keychain_checkbox.setButtonType_(NSSwitchButton)
        self.keychain_checkbox.cell().setTitle_('Save to Keychain')
        self.keychain_checkbox.cell().setBordered_(False)
        self.keychain_checkbox.cell().setEnabled_(True)
        self.keychain_checkbox.cell().setState_(True)

        # add various objects as subviews
        accessory_view.addSubview_(self.keychain_checkbox)
        accessory_view.addSubview_(username_label)
        accessory_view.addSubview_(self.username_field)
        accessory_view.addSubview_(password_label)
        accessory_view.addSubview_(self.password_field)

        # add custom view to alert dialog
        self.alert.setAccessoryView_(accessory_view)


    def display(self):
        ''' displays the dialog and returns True is user clicked "ok" or
            False if user clicked "cancel"'''
        self.response = True if self.alert.runModal() == 1000 else False
        return self.response


    def username(self):
        ''' return the value of the username field'''
        return self.username_field.stringValue()


    def password(self):
        ''' return the value of the password field'''
        return self.password_field.stringValue()


    def save(self):
        ''' return True if checkbox if selected '''
        return True if self.keychain_checkbox.state() else False
