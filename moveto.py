import requests
from requests.auth import HTTPBasicAuth
import re
from StringIO import StringIO

JIRA_URL = 'http://bigdata8.ddns.net:8008'
JIRA_ACCOUNT = ('alex', '12345trewq')
# the JIRA project ID (short)
JIRA_PROJECT = 'DEV'
GITLAB_URL = 'https://bigdata8.ddns.net/gitlab/'
# this token will be used whenever the API is invoked and
# the script will be unable to match the jira's author of the comment / attachment / issue
# this identity will be used instead.
GITLAB_TOKEN = 'X3AcpnasE9pPHfknxSpy'
# the project in gitlab that you are importing issues to.
GITLAB_PROJECT = 'namespaced/project/dev'
# the numeric project ID. If you don't know it, the script will search for it
# based on the project name.
GITLAB_PROJECT_ID = None
# set this to false if JIRA / Gitlab is using self-signed certificate.
VERIFY_SSL_CERTIFICATE = False

# IMPORTANT !!!
# make sure that user (in gitlab) has access to the project you are trying to
# import into. Otherwise the API request will fail.

# jira user name as key, gitlab as value
# if you want dates and times to be correct, make sure every user is (temporarily) admin
GITLAB_USER_NAMES = {
    'alex': 'user',
}

jira_issues = requests.get(
    JIRA_URL + 'rest/api/2/search?jql=project=%s+&maxResults=10000' % JIRA_PROJECT,
    auth=HTTPBasicAuth(*JIRA_ACCOUNT),
    verify=VERIFY_SSL_CERTIFICATE,
    headers={'Content-Type': 'application/json'}
)

if not GITLAB_PROJECT_ID:
    # find out the ID of the project.
    for project in requests.get(
        GITLAB_URL + 'api/v4/projects',
        headers={'PRIVATE-TOKEN': GITLAB_TOKEN},
    ).json():
        if project['path_with_namespace'] == GITLAB_PROJECT:
            GITLAB_PROJECT_ID = project['id']
            break

if not GITLAB_PROJECT_ID:
    raise Exception("Unable to find %s in gitlab!" % GITLAB_PROJECT)

for issue in jira_issues.json()['issues']:
    
    reporter = issue['fields']['reporter']['name']

    gl_issue = requests.post(
        GITLAB_URL + 'api/v3/projects/%s/issues' % GITLAB_PROJECT_ID,
        headers={'PRIVATE-TOKEN': GITLAB_TOKEN,'SUDO': GITLAB_USER_NAMES.get(reporter, reporter)},
        verify=VERIFY_SSL_CERTIFICATE,
        data={
            'title': issue['fields']['summary'],
            'description': issue['fields']['description'],
            'created_at': issue['fields']['created']
        }
    ).json()['id']

    # get comments and attachments
    issue_info = requests.get(
        JIRA_URL + 'rest/api/2/issue/%s/?fields=attachment,comment' % issue['id'],
        auth=HTTPBasicAuth(*JIRA_ACCOUNT),
        verify=VERIFY_SSL_CERTIFICATE,
        headers={'Content-Type': 'application/json'}
    ).json()

    for comment in issue_info['fields']['comment']['comments']:
        author = comment['author']['name']

        note_add = requests.post(
            GITLAB_URL + 'api/v3/projects/%s/issues/%s/notes' % (GITLAB_PROJECT_ID, gl_issue),
            headers={'PRIVATE-TOKEN': GITLAB_TOKEN,'SUDO': GITLAB_USER_NAMES.get(author, author)},
            verify=VERIFY_SSL_CERTIFICATE,
            data={
                'body': comment['body'],
                'created_at': comment['created']
            }
        )

    if len(issue_info['fields']['attachment']):
        for attachment in issue_info['fields']['attachment']:
            author = attachment['author']['name']

            _file = requests.get(
                attachment['content'],
                auth=HTTPBasicAuth(*JIRA_ACCOUNT),
                verify=VERIFY_SSL_CERTIFICATE,
            )

            _content = StringIO(_file.content)

            file_info = requests.post(
                GITLAB_URL + 'api/v3/projects/%s/uploads' % GITLAB_PROJECT_ID,
                headers={'PRIVATE-TOKEN': GITLAB_TOKEN,'SUDO': GITLAB_USER_NAMES.get(author, author)},
                files={
                    'file': (
                        attachment['filename'],
                        _content
                    )
                },
                verify=VERIFY_SSL_CERTIFICATE
            )

            del _content

            # now we got the upload URL. Let's post the comment with an
            # attachment
            requests.post(
                GITLAB_URL + 'api/v3/projects/%s/issues/%s/notes' % (GITLAB_PROJECT_ID, gl_issue),
                headers={'PRIVATE-TOKEN': GITLAB_TOKEN,'SUDO': GITLAB_USER_NAMES.get(author, author)},
                verify=VERIFY_SSL_CERTIFICATE,
                data={
                    'body': file_info.json()['markdown'],
                    'created_at': attachment['created']
                }
            )

    print "created issue #%s" % gl_issue

print "imported %s issues from project %s" % (len(jira_issues.json()['issues']), JIRA_PROJECT)
