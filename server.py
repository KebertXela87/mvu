import psycopg2
import psycopg2.extras
import os, uuid, re
from flask import Flask, render_template, request, redirect, url_for, session, Markup, json, send_from_directory
import flask_login
from flask_login import current_user
from flask_socketio import SocketIO, emit
from werkzeug import secure_filename
from parse import Parser
from sim import Simulation
from flask_mail import Mail, Message
  
app = Flask(__name__)
app.secret_key = os.urandom(24).encode('hex')

app.config['MAIL_SERVER']='smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = 'mvuwebapp@gmail.com'
app.config['MAIL_PASSWORD'] = 'mvuwebapppass'
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True

# This is the path to the upload directory, In cloud9 it sends the file to a folder named uploads
# Not needed since a parser will be used
# app.config['UPLOAD_FOLDER'] = 'uploads/'

# Only files containing these extensions will be accepted
app.config['ALLOWED_EXTENSIONS'] = set(['xls', 'xlsx', 'csv', 'xlsm', 'xlt', 'xml'])

mail = Mail(app)
socketio = SocketIO(app)

login_manager = flask_login.LoginManager()
login_manager.init_app(app)

dataUploadStorage = {}


class User(flask_login.UserMixin):
    pass
    
def connectToDB():
    connectionString = 'dbname=mousedb user=owner password=41PubBNmfQhmfCNy host=localhost'
    #print connectionString
    try:
        return psycopg2.connect(connectionString)
    except:
        print("Can't connect to database")

# setup all of the values from the users table for the current user
def setup_User(user, data):
    user.id = data['username']

    
# This is a function to help bring a location map json back from the database and turn it back into a dictionary   
def convertString(longstring):
    final = {}
    done = False
    counter = 0
   # print(longstring)
    while counter < len(longstring):
        if longstring[counter] == "{" or longstring[counter] == "}":
            counter += 1
        else:
            thiskey = ""
            thisvalue = ""
            #print("skipping: " + longstring[counter])
            counter += 1
            while not done:
                thiskey += longstring[counter]
                counter += 1
                if longstring[counter] == '"':
                    done = True
            done = False
            counter += 4
            while longstring[counter] != '"':
                thisvalue += longstring[counter]
                counter += 1
            counter += 3
            final[thiskey]=thisvalue
    return final

# this is a function to help bring a heat map data json from the database and turn it back into a dictionary
def convertHeatString(longstring):
    final = {}
    done = False
    counter = 2
    while not done:
        thisKey = ""
        while longstring[counter] !='"':
            thisKey += longstring[counter]
            counter += 1
        final[thisKey] = {}
        counter += 5
        secondDone = False
        while not secondDone:
            lockey = ""
            while longstring[counter] != '"':
                lockey += longstring[counter]
                counter += 1
            counter += 3
            value = ""
            while longstring[counter] != ',' and longstring[counter] != '}':
                value += longstring[counter]
                counter += 1
            final[thisKey][lockey] = int(value)
            if longstring[counter] == '}':
                secondDone = True
                counter += 1
            else:
                counter += 3
        if longstring[counter] == '}':
            done = True
        else:
            counter += 4
    return final
    
# this is a function to help bring a vector map data json from the database and turn it back into a dictionary
def convertVectorString(longstring):
    final = {}
    done = False
    counter = 2
    while not done:
        thisKey = ""
        while longstring[counter] !='"':
            thisKey += longstring[counter]
            counter += 1
        final[thisKey] = []
        counter += 6
        secondDone = False
        while not secondDone:
            lockey = ""
            while longstring[counter] != '"':
                lockey += longstring[counter]
                counter += 1
            counter += 3
            value = ""
            while longstring[counter] != ']':
                value += longstring[counter]
                counter += 1
            thisEntry = []
            thisEntry.append(lockey)
            thisEntry.append(int(value))
            final[thisKey].append(thisEntry)
            counter += 1
            if longstring[counter] == ']':
                secondDone = True
                counter += 1
            else:
                counter += 4
        if longstring[counter] == '}':
            done = True
        else:
            counter += 3
    #print(final)
    return final
    
    
    # For a given file, return whether it's an allowed type or not
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in app.config['ALLOWED_EXTENSIONS']


def parseLocations(rows, cols, setData):
    locations = {}
    locations["rows"] = str(rows)
    locations["columns"] = str(cols)
    for i in range(int(rows)):
        for j in range(int(cols)):
            thisIndex = (i * int(cols)) + j
            locations[str(thisIndex)] = str(setData[thisIndex])
    return locations         

@login_manager.user_loader
def user_loader(user_id):
    db = connectToDB()
    cur= db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM users WHERE username = %s;", (user_id,))
    data = cur.fetchone()
    if data is not None:
        user = User()
        setup_User(user, data)
        return user
        
    return #no user

@app.route('/logout')
def logout():
    flask_login.logout_user()
    return redirect(url_for('index'))

# the page to go to if a login is required and no one is loged in.
@login_manager.unauthorized_handler
def unauthorized_handler():
    return render_template('login.html', login_failed = 'true', currentpage='login')
        
@app.route('/', methods=['GET', 'POST']) #handle login
def index():
    
    if request.method == 'GET':
        if current_user.is_authenticated:
            return render_template('index.html', login_failed='false', currentpage='home', admin=session["admin"])
        else:
            return render_template('login.html', login_failed='false', currentpage='login')

    #attempt login
    db = connectToDB()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    usernameinput = request.form['username']
    passwordinput = request.form['password']
   
    cur.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(%s) AND password = crypt(%s, password);", (usernameinput, passwordinput))
    if cur.fetchone():
        user = User()
        user.id = usernameinput
        flask_login.login_user(user)
        
        cur.execute("SELECT admin FROM users WHERE LOWER(username) = LOWER(%s) AND password = crypt(%s, password);", (usernameinput, passwordinput))
        admin = cur.fetchall()
        for row in admin:
            print "   xxx   xxx   xxx", admin[0]
        session["admin"]=admin[0]    
        return render_template('index.html', login_failed='false', currentpage='login', admin=session["admin"])

    #login failed
    return render_template('login.html', login_failed = 'true', currentpage='login')


@app.route('/maps')
@flask_login.login_required
def maps():
    db = connectToDB()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    return render_template('maps.html', currentpage='maps', admin=session["admin"])
    
@app.route('/data', methods=["GET", "POST"])
@flask_login.login_required
def data():
    if request.method == 'POST':
        file = request.files['file']
        #Check if the file is one of the allowed types/extensions
        if file and allowed_file(file.filename):
            # Remove unsupported chars from filename
            filename = secure_filename(file.filename)
            #print("Through here.")
            
            # The variable called file stores the file, this could be sent to the parser rather than being saved
            # Nothing withing this if statement is needed for parsing purposes. I am leaving it to show
            # functionality if you want to test it.
            # Move the file form the temporal folder to the upload folder
            
            myData = Parser(file).getData()
            session["currentlyUploading"] = True
            print(session.keys())
            dataUploadStorage[session["user_id"]] = myData["data"]
            
            #print(myData["data"])
            #session["uploadingData"] = myData["data"] 
            session["uploadingFileName"] = myData["filename"] 
            #print("Done parsing.")
    #        print(session["currentlyUploading"])
    #        print(session["uploadingData"])
    #        print(session["uploadingFileName"])
    else:
        session["uploadingFileName"] = ""
        session["currentlyUploading"] = False
        if session["user_id"] in dataUploadStorage.keys():
            del dataUploadStorage[session["user_id"]]
    return render_template('data.html', currentpage='data', admin=session["admin"])
    
@app.route('/users', methods=['GET', 'POST'])
@flask_login.login_required
def manageusers():
    db = connectToDB()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    cur.execute("SELECT * FROM users")
    userdata = cur.fetchall()
    session["userdata"]=userdata
    
    return render_template('users.html', currentpage='users', userdata=userdata, admin=session["admin"])

@app.route('/sendpassword', methods=['GET', 'POST'])
def send_password():
    db = connectToDB()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    if request.method == 'GET':
        return render_template('send_password.html', currentpage = 'send_password')
        
    # get email from form
    email = request.form['email']
    print "User email is ."+email

    # check to see if user exists
    print "Checking username...."
    cur.execute("SELECT email FROM users WHERE email = %s;", (email,))
    if cur.fetchone():
        print "Checking password...."
        # cur.execute("SELECT INTO users password VALUES (crypt(%s, gen_salt('bf')) WHERE username = %s);", (password, username,))

        cur.execute("SELECT password = crypt('password', gen_salt('bf')) FROM users WHERE email = %s;", (email,))
        password = cur.fetchall()
        print password
        print password
        print password
        print password
            
        msg = Message('MVU Password', sender = 'mvuwebapp@yahoo.com', recipients = [email])
        msg.body = "Hello, this is yot password- "+str(password) 
        mail.send(msg)
        
        print "Mail Sent."
    else:
        return render_template('send_password.html', currentpage='change_password', bad_account='badusername', account_created='false')
            
    return render_template('password_sent.html', currentpage='send_password', email=email, bad_account='unknown')

################################################################################
############################ File Upload Functions #############################
################################################################################


################################################################################
################################## SOCKET IO ###################################
################################################################################


@socketio.on('connect', namespace='/heatmap')
def makeConnection(): 
    print('connected')
    
#UPLOAD FUNCTIONS
@socketio.on('finishUpload', namespace='/heatmap')
def uploadData(setData):
    mySimulation = Simulation()
    mySimulation.setUp(dataUploadStorage[session["user_id"]])
    mySimulation.runFullSim()
    thesePaths = mySimulation.getAllPaths()
    theseHeatMaps = mySimulation.getAllHeatData()
    thisFileName = str(setData[0])
    rows = str(setData[1])
    cols = str(setData[2])
    getLocations = parseLocations(rows, cols, setData[3])
    db = connectToDB()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("INSERT INTO datasets (datasetname, userid, heatdata, vectordata, locationmap) VALUES (%s, %s, %s, %s, %s)", (thisFileName, 1, json.dumps(theseHeatMaps), json.dumps(thesePaths), json.dumps(getLocations)))
    db.commit()
    session["currentlyUploading"] = False
    del dataUploadStorage[session["user_id"]]
    session["uploadingFileName"] = ""
    emit('finishedUploading')
        
@socketio.on('getSetName', namespace='/heatmap')
def getSetName():
    #print("Tried to get a set name.")
    emit('haveSetName', session["uploadingFileName"])
    
@socketio.on('checkUploading', namespace='/heatmap')
def checkIfUploading():
    #print(session["currentlyUploading"])
    if "currentlyUploading" in session.keys():
        emit('checkedUploading', session["currentlyUploading"])
    else:
        emit('checkedUploading', False)

#USER FUNCTIONS
@socketio.on('getUsers', namespace='/heatmap')
def getUsers():
    db = connectToDB()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute("SELECT * FROM users")
    results = cur.fetchall()
    
    userdata = []
    
    if(len(results) > 0):
        for result in results:
            # result[1] = username, result[3] = email, result[4] = admin
            adminValue = "No"
            if result[4]:
                adminValue = "Yes"
            user = {'name': result[1], 'admin': adminValue, 'email': result[3]}
            userdata.append(user)
        
        emit('returnUsers', userdata)
    else:
        print("Error retrieving users from database...");

@socketio.on('createDaUser', namespace='/heatmap')
def createDaUser(formdata):
    db = connectToDB()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # user variables
    username = formdata['username']
    password = formdata['password']
    email = formdata['email']
    usertype = formdata['usertype']
    
    # check usertype
    if usertype == "user":
        usertype = "false"
    else:
        usertype = "true"
    
    # Check for username
    print("Checking username....")
    usernameExists = False
    checkUserQuery = "SELECT username FROM users WHERE username = %s;"
    cur.execute(checkUserQuery, (username,))
    if cur.fetchone():
        #username found - throw error
        error_message = "Sorry, the username '" + username + "' already exists!"
        print(error_message)
        emit('loadMessageBox', error_message)
        usernameExists = True
    
    # Attempt to create user
    if not usernameExists:
        usernameInsertGood = True
        print("Attempting to create user....")
        try:
            createUserQuery = "INSERT INTO users (username, password, email, admin) VALUES (%s, crypt(%s, gen_salt('bf')), %s, %s);"
            cur.execute(createUserQuery, (username, password, email, usertype))
        except:
            usernameInsertGood = False
            errormessage = "Whoops! User Creation Failed!"
            print(errormessage)
            emit('loadMessageBox', errormessage)
            db.rollback()
        db.commit()
        
        # Check to see if user was created
        if usernameInsertGood:
            print("Checking success of user creation....")
            cur.execute(checkUserQuery, (username,))
            if cur.fetchone():
                # user created
                success_message = "User created!"
                print(success_message)
                emit('loadMessageBox', success_message)
            else:
                errormessage = "Whoops! User Creation Failed!"
                print(errormessage)
                emit('loadMessageBox', errormessage)

@socketio.on('changeUserPassword', namespace='/heatmap')
def changeUserPassword(changeformdata):
    db = connectToDB()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    username = changeformdata['username']
    password = changeformdata['password']
    matchpassword = changeformdata['matchpassword']
    
    # Check to see if user exists
    print("Checking for username....")
    errorCheckPass = False
    checkUserQuery = "SELECT username FROM users WHERE username = %s;"
    cur.execute(checkUserQuery, (username,))
    if cur.fetchone():
        print("Username found")
        errorCheckPass = True
    else:
        errorMessage = "ERROR: Username not found."
        print(errorMessage)
        emit('loadMessageBox', errorMessage);
    
    # make sure passwords match
    if password != matchpassword:
        errorMessage = "ERROR: Passwords don't match."
        print(errorMessage)
        emit('loadMessageBox', errorMessage);
        errorCheckPass = False
    
    # try to insert new password
    try:
        print("Inserting password...")
        passwordInsertQuery = "UPDATE users SET password = crypt(%s, gen_salt('bf')) WHERE username = %s;"
        cur.execute(passwordInsertQuery, (password, username))
        success_message = "Password changed!"
        emit('loadMessageBox', success_message)
    except:
        errorMessage = "ERROR: Problem updating password..."
        print(errorMessage)
        emit('loadMessageBox', errorMessage)
        db.rollback()
    db.commit()
        
@socketio.on('deleteUser', namespace='/heatmap')
def deleteUser(username):
    db = connectToDB()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    testDeletion = True
    
    # Make sure user exists in database
    print("Checking for username in database....")
    cur.execute("SELECT username FROM users WHERE username = %s;", (username,))
    if cur.fetchone():
        print("Username is found.")
    else:
        # send message alerting user to error
        message = "User '" + username + "' not found."
        emit('loadMessageBox', message)
        testDeletion = False
        
    # Attempt to delete user
    print("Attempting to delete user....")
    try:
        query = "DELETE FROM users WHERE username = %s;"
        
        # Check to see if current user is deleting themself
        selfdeletion = False
        if current_user.id == username:
            flask_login.logout_user()
            selfdeletion = True
        
        # Check to see if more than one admin
        dontDeleteLastAdmin = False
        if selfdeletion:
            print("CHECKING FOR ADMIN COUNT")
            cur.execute("SELECT admin FROM users WHERE admin = 't';")
            result = cur.fetchall()
            if len(result) < 2:
                dontDeleteLastAdmin = True # if user is last admin do not delete them.
        
        if dontDeleteLastAdmin:
            # send message alerting user to last admin rule
            message = "You cannot delete the last Admin User."
            print(message)
            emit('loadMessageBox', message)
            testDeletion = False
        else:
            print(cur.mogrify(query, (username,)))
            cur.execute(query, (username,))
            
    except:
        print("Error deleting user...")
        if selfdeletion:
            user = User()
            user.id = username
            flask_login.login_user(user)
        # send message alerting user to error
        message = "Error deleting user " + username + " from database."
        emit('loadMessageBox', message)
        testDeletion = False
        db.rollback()
    db.commit()
    
    if testDeletion:
        # Check to make sure user was deleted
        print("Checking success of user deletion....")
        cur.execute("SELECT username FROM users WHERE username = %s;", (username,))
        if cur.fetchone():
            # user not deleted
            print("User not deleted")
            # send message alerting user to this fact
            message = "Error deleting user " + username + " from database."
            emit('loadMessageBox', message)
        else:
            print("User deleted")
            if selfdeletion:
                print("I DELETED MYSELF")
                emit('redirect', {'url': url_for('index')})
            else:
                message = username + " has been deleted!"
                emit('loadMessageBox', message)

#MAP FUNCTIONS
@socketio.on('getDatasetNames', namespace='/heatmap')
def getDatasetNames():
    print("Getting names!!!!")
    db = connectToDB()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    # get dataset names from database
    datasetnames = "SELECT datasetname AS name FROM datasets;"
    cur.execute(datasetnames)
    results = cur.fetchall()
    
    test = []
    
    if(len(results) > 0):
        for result in results:
            tmp = {'name': result[0] }
            test.append(tmp)
    
        for i in test:
            emit('datasetnamelist', i)
            
@socketio.on('loadMice', namespace='/heatmap')
def loadMice(dataset):
    db = connectToDB()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    # grab the dataset for the passed selection
    getDataset = "SELECT heatdata FROM datasets WHERE datasetname = %s;"
    #print(getDataset % ("%%" + dataset + "%%"))
    # cur.execute(getDataset, ("%%" + dataset + "%%"))
    cur.execute("SELECT heatdata FROM datasets WHERE datasetname = '%s';" % (dataset))
    result = cur.fetchone()
    cur.execute("SELECT vectordata FROM datasets WHERE datasetname = '%s';" % (dataset))
    vecresult = cur.fetchone()
    cur.execute("SELECT locationmap FROM datasets WHERE datasetname = '%s';" % (dataset))
    locresult = cur.fetchone()
    
    emit('returnDataset', {
        'data': {
            'heatdata': result,
            'vectdata': vecresult,
            'mapping': locresult
        }
    })

if __name__ == '__main__':
    socketio.run(app, host=os.getenv('IP', '0.0.0.0'), port=int(os.getenv('PORT', 8080)), debug = True)
    
    

# Stuff I'm saving ... but can probably delete - Justin

    
#def getAllDataSets():
#    db = connectToDB()
#    cur= db.cursor(cursor_factory=psycopg2.extras.DictCursor)
#    cur.execute("SELECT datasetname FROM datasets;", )
#    holddata = cur.fetchall()
#    allsets = []
#    for line in holddata:
#        allsets.append(line[0])
#    return allsets

    
#def parseUploadForm(form):
#    parsedData = {}
#    locations = {}
#    oldSet = False
#    if "oldSet" in form.keys():
#        oldSetName = str(form["prevSetName"])
#        oldSet = True
#        locations["oldSet"] = oldSetName
#    else:
#        for i in range(7):
#            for j in range(7):
#                oldKey = "[" + str(i) + ", " + str(j) + "]"
#                newKey = (i * 7) + j
#                value = form[oldKey]
#                if str(value) != "-1":
#                    locations[str(newKey)] = str(value)
#                
#    parsedData["locations"] = locations
#    parsedData["filename"] = str(form["setName"])
#    parsedData["datalines"] = User.uploadingData
#    return parsedData  
    
#def parseUpdatedForm(form):
#    parsedData = {}
#    locations = {}
#    oldSet = False
#    if "oldSet" in form.keys():
#        oldSetName = str(form["prevSetName"])
#        db = connectToDB()
#        cur= db.cursor(cursor_factory=psycopg2.extras.DictCursor)
#        cur.execute("SELECT locationmap from datasets where datasetname=%s", (oldSetName,))
#        holdlocations = cur.fetchall()
#        tempLocations = holdlocations[0][0]
#        locations = convertString(tempLocations)  
#    else:
#        for i in range(49):
#            value = form[str(i)]
#            if str(value) != "-1":
#                locations[str(i)]=str(value)
                
    #print(form["setName"])
#    if form["setName"] == "":
#        parsedData["setName"] = User.viewingData
#    else:
#        parsedData["setName"] = form["setName"]
        
#    parsedData["locations"] = locations
#    return parsedData

#@app.route('/setDataUpload', methods=['POST'])
#def setDataUpload():
#    myData = parseUploadForm(request.form)
#    mySimulation = Simulation()
#    mySimulation.setUp(myData["datalines"])
#    mySimulation.runFullSim()
#    thesePaths = mySimulation.getAllPaths()
#    theseHeatMaps = mySimulation.getAllHeatData()
#    if myData["filename"] == "":
#        myData["filename"] = User.uploadingFileName
    
#    db = connectToDB()
#    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
#    print(myData["locations"].keys())
#    if "oldSet" in myData["locations"].keys():
#        print(myData["locations"]["oldSet"])
#        oldLoc = myData["locations"]["oldSet"]
#        cur.execute("SELECT locationmap from datasets where datasetname=%s", (oldLoc,))
#        holdlocations = cur.fetchall()
#        tempLocations = holdlocations[0][0]
#        getLocations = convertString(tempLocations)
#    else:
#        getLocations = myData["locations"]
    
#    db = connectToDB()
#    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
#    cur.execute("INSERT INTO datasets (datasetname, userid, heatdata, vectordata, locationmap) VALUES (%s, %s, %s, %s, %s)",(myData["filename"], 1, json.dumps(theseHeatMaps), json.dumps(thesePaths), json.dumps(getLocations)))
#    db.commit()
#    return viewDataPage(getDataToView(myData["filename"]))
    
#def viewDataPage(data):
#    return render_template('viewdata.html', myData=data, otherDataSets=getAllDataSets(), admin=session["admin"])

#def getDataToView(setName):
#    db = connectToDB()
#    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
#    cur.execute("SELECT * from datasets WHERE datasetname = %s", (setName,))
#    thisData = cur.fetchall()
#    if len(thisData) != 1:
#        otherDataSets = getAllDataSets()
#        return render_template('data.html', currentpage='data', otherDataSets=getAllDataSets(), admin=session["admin"])
#    User.viewingData=setName
#    formattedData = {}
#    formattedData["setName"] = str(setName)
#    formattedData["heatData"] = convertHeatString(thisData[0][3])
#    formattedData["vectorData"] = convertVectorString(thisData[0][4])
#    formattedData["datasetname"] = thisData[0][6]
#    allLocations = []
#    for i in range(1, 26):
#            if i < 10:
#                allLocations.append("RFID0" + str(i))
#            else:
#                allLocations.append("RFID" + str(i))
#    formattedData["alllocations"] = allLocations
#    assembleMap = []
#    rowCounter = 0
#    rowNames = ["firstRow", "secondRow", "thirdRow", "fourthRow", "fifthRow", "sixthRow", "seventhRow"]
#    rawLocations = convertString(thisData[0][5])
    
#    formattedData["rowMap"] = {}
#    for name in rowNames:
#        formattedData["rowMap"][name] = []
#    for i in range (49):
#        if i > 0 and i % 7 == 0:
#            rowCounter += 1
#        entry = {}
#        entry["index"] = i
#        if str(i) in rawLocations.keys():
#            entry["value"] = rawLocations[str(i)]
#        else:
#            entry["value"] = "--"
#        formattedData["rowMap"][rowNames[rowCounter]].append(entry)
#    return formattedData