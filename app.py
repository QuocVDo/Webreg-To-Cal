from __future__ import print_function
import os
from flask import Flask, render_template, request, redirect, url_for
from werkzeug import secure_filename

import datetime
import pickle
import os.path
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

import webbrowser, os
import json
import boto3
import io
from io import BytesIO
import sys
from pprint import pprint

import cgi

num_weeks = 10
start_date = '2019-09-23'
# start_date = '2019-11-2'

# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/calendar']


def translate_txt(file):
    f = open(file)
    name = ''
    cname = ''
    data = []
    for line in f:
        l = line.split()
        if l == []:
            continue
        if l[0] == 'Expand:':
            name = ' '.join(l[1:])
            continue
        if l[-1] == 'Enrolled':
            c1 = 0
            c2 = 0
            for i in range(len(l)):
                x = l[i]
                if len(x) == 3 and x[0].isupper() and not x[1].isalpha() and not x[2].isalpha():
                    c1 = i
                if len(x) == 4 and x[1] == '.' and x[2] == x[3] and x[2] == '0':
                    c2 = i
            l = [l[0] + ' ' + l[1]] + [' '.join(l[2:c1])] + [' '.join(l[c1 + 2:c2 - 1])] + l[c2 + 1:-1]
            cname = l[0]
            l[0] += " Class"
        else:
            if not name == '':
                l = [name] + l
                name = ''
            date = -1
            dash = -1
            for i in range(len(l)):
                if '/' in l[i]:
                    date = i
                if '-' in l[i]:
                    dash = i
            if not date == -1:
                l = [' '.join([cname] + l[:date - 2]), '', ''] + [l[date - 1] + ' ' + l[date]] + l[date + 1:]
            else:
                l = [cname, '', ''] + l[dash - 1:]
                if name == '':
                    l[0] += " Discussion"
                else:
                    l[0] += " " + name
                    name = ''
        if l[4] == 'TBA':
            continue
        data.append(l)
    return data


def translate_cvs(file):
    f = open(file)
    data = []
    name = ''
    l0 = ''
    last_course = 0
    for line in f:
        l = []
        for x in line.split('",'):
            l.append(x[1:-1])
        if l[0] == 'Subject Course':
            continue
        l = l[:2] + [l[4]] + l[7:11]
        if l[4] == '' or l[4] == 'TBA':
            name = l[1]
            continue
        if l[0] == '':
            if l[1] == '':
                if last_course == 1:
                    name = 'Discussion'
                if name == '':
                    continue
                l[0] = l0 + ' ' + name
                name = ''
            else:
                l[0] = l0 + ' ' + l[1]
                l[1] = ''
        else:
            l0 = l[0]
            l[0] += " Class"
            last_course = 0
        last_course += 1
        data.append(l)
    return data


def translate_vcs(file):
    f = open(file)
    data = []
    name = ''
    l0 = ''
    last_course = 0
    for line in f:
        l = []
        for x in line.split('|')[:11]:
            l.append(x[:-1])
        if ''.join(line.split('|')[:-1]) == '':
            continue

        l = l[:2] + [l[4]] + l[7:11]

        if l[4] == '' or l[4] == 'TBA':
            name = l[1]
            continue
        if l[0] == '':
            if l[1] == '':
                if last_course == 1:
                    name = 'Discussion'
                if name == '':
                    continue
                l[0] = l0 + ' ' + name
                name = ''
            else:
                l[0] = l0 + ' ' + l[1]
                l[1] = ''
        else:
            l0 = l[0]
            l[0] += " Class"
            last_course = 0
        last_course += 1
        data.append(l)
    return data


def translate_time(x):
    first, second = x[:-1].split(":")
    add = 0
    if x[-1] == 'p':
        if not first == '12':
            add = 12
    first = str(int(first) + add)
    if len(first) == 1:
        first = "0" + first
    return first + ":" + second + ":00"


def translate_weekdays(line):
    ans = ''
    day = ''
    for i in range(len(line)):
        day += line[i]
        if line[i] in 'MWFuha':
            res = ''
            if day == 'M':
                res = 'MO'
            elif day == 'Tu':
                res = 'TU'
            elif day == 'W':
                res = 'WE'
            elif day == 'Th':
                res = 'TH'
            elif day == 'F':
                res = 'FR'
            elif day == 'Sa':
                res = 'SA'
            elif day == 'Su':
                res = 'SU'
            ans += res + ','
            day = ''
    return ans[:-1]


def translate_line(line):
    # class_name class_des prof_name MWF start-end build number

    # start and end times
    startd, endd = line[4].split("-")
    startd = translate_time(startd)
    endd = translate_time(endd)

    # number of classes in a quarter
    count = 0
    for x in line[3]:
        if x.isupper():
            count += 1
    count *= num_weeks

    des = ''
    if not line[1] + line[2] == '':
        des = line[1] + ' with professor ' + line[2]

    # if its a final or a midterm

    ddate = start_date
    hi = line[3].split(" ")
    if len(hi) == 2:
        mm, dd, yy = hi[1].split("/")
        ddate = "-".join([yy, mm, dd])
        count = 1
        line[3] = hi[0]

    weekdays = translate_weekdays(line[3])

    event = {
        'summary': line[0],
        'location': line[5] + ' ' + line[6],
        'description': des,
        'start': {
            'dateTime': ddate + 'T' + startd,
            'timeZone': 'America/Los_Angeles',
        },
        'end': {
            'dateTime': ddate + 'T' + endd,
            'timeZone': 'America/Los_Angeles',
        },
        'recurrence': [
            'RRULE:FREQ=WEEKLY;COUNT=' + str(count) + ';BYDAY=' + weekdays
        ],
    }

    return event


def init():
    """Shows basic usage of the Google Calendar API.
    Prints the start and name of the next 10 events on the user's calendar.
    """
    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    '''if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:'''

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(
            'credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)
    # Save the credentials for the next run
    with open('token.pickle', 'wb') as token:
        pickle.dump(creds, token)

    service = build('calendar', 'v3', credentials=creds)
    return service


def add_class(service, data):
    event = service.events().insert(calendarId='primary', body=data).execute()
    return ('Event created: %s' % (event.get('htmlLink')))


def start():
    data = translate_vcs('output.csv')
    # data = translate_txt('webregtext.txt')
    service = init()
    for line in data:
        event = translate_line(line)
        print(event)
        add_class(service, event)


app = Flask(__name__)

def get_rows_columns_map(table_result, blocks_map):
    rows = {}
    for relationship in table_result['Relationships']:
        if relationship['Type'] == 'CHILD':
            for child_id in relationship['Ids']:
                cell = blocks_map[child_id]
                if cell['BlockType'] == 'CELL':
                    row_index = cell['RowIndex']
                    col_index = cell['ColumnIndex']
                    if row_index not in rows:
                        # create new row
                        rows[row_index] = {}

                    # get the text value
                    rows[row_index][col_index] = get_text(cell, blocks_map)
    return rows


def get_text(result, blocks_map):
    text = ''
    if 'Relationships' in result:
        for relationship in result['Relationships']:
            if relationship['Type'] == 'CHILD':
                for child_id in relationship['Ids']:
                    word = blocks_map[child_id]
                    if word['BlockType'] == 'WORD':
                        text += word['Text'] + ' '
                    if word['BlockType'] == 'SELECTION_ELEMENT':
                        if word['SelectionStatus'] == 'SELECTED':
                            text += 'X '
    return text


def get_table_csv_results(file_name):
    with open(file_name, 'rb') as file:
        img_test = file.read()
        bytes_test = bytearray(img_test)
        print('Image loaded', file_name)

    # process using image bytes
    # get the results
    client = boto3.client('textract')

    response = client.analyze_document(Document={'Bytes': bytes_test}, FeatureTypes=['TABLES'])

    # Get the text blocks
    blocks = response['Blocks']
    # print(blocks)

    blocks_map = {}
    table_blocks = []
    for block in blocks:
        blocks_map[block['Id']] = block
        if block['BlockType'] == "TABLE":
            table_blocks.append(block)

    if len(table_blocks) <= 0:
        return "<b> NO Table FOUND </b>"

    print(table_blocks)

    csv = ''
    for index, table in enumerate(table_blocks):
        csv += generate_table_csv(table, blocks_map, index + 1)
        csv += '\n\n'

    return csv


def generate_table_csv(table_result, blocks_map, table_index):
    rows = get_rows_columns_map(table_result, blocks_map)

    table_id = 'Table_' + str(table_index)

    # get cells.
    # csv = 'Table: {0}\n\n'.format(table_id)
    csv = ''

    for row_index, cols in rows.items():

        for col_index, text in cols.items():
            csv += '{}'.format(text) + "|"
        csv += '\n'

    csv += '\n\n\n'
    return csv


def main(file_name):
    table_csv = get_table_csv_results(file_name)

    output_file = 'output.csv'

    # replace content
    with open(output_file, "wt") as fout:
        fout.write(table_csv)

    # show the results
    print('CSV OUTPUT FILE: ', output_file)




@app.route('/')
def home():
    return render_template("home.html")

@app.route('/about')
def about():
    return render_template("about.html")

@app.route('/salvador')
def salvador():
    return 'Hello Salvador!'

@app.route('/upload')
def upload():
    return render_template("upload.html")

@app.route('/uploader', methods = ['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        f = request.files['file']
        print(secure_filename(''))
        file_name = os.getcwd()+secure_filename(f.filename)
        f.save(file_name)

        table_csv = get_table_csv_results(file_name)
        output_file = 'output.csv'
        with open(output_file, "wt") as fout:
            fout.write(table_csv)

        data = translate_vcs(output_file)
        service = init()
        for line in data:
            event = translate_line(line)
            print(event)
            add_class(service, event)

        return 'file uploaded successfully'

    return ''

if __name__ == '__main__':
    app.run(debug=True)
