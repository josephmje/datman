#!/usr/bin/env python
"""
Uploads a scan archive to XNAT

Usage: 
    xnat-upload.py [options] -u USER <project> <archive>
    xnat-upload.py [options] -c FILE <project> <archive>

Arguments:
    <project>             Study/Project name 
    <archive>             Properly named zip file

Options: 
    --server URL          XNAT server to connect to
                          [default: http://da55.pet.utoronto.ca:5004/spred]

    -c,--credfile FILE    File containing XNAT username and password. The
                          username should be on the first line, and password
                          on the next.

    -u,--username USER    XNAT username. If specified then the credentials
                          file is ignored and you are prompted for password.

    -v,--verbose          Be chatty

"""
import requests
from docopt import docopt
import datman as dm
import datman.utils
import datman.scanid
import os.path
import zipfile
import dicom as dcm
import io
import sys
import getpass

CREATE_URL = "{server}/REST/projects/{project}/subjects/{subject}"

UPLOAD_URL = "{server}/data/services/import?" \
             "project={project}&subject={subject}&session={session}" \
             "&overwrite=delete&prearchive=false&inbody=true" 

ATTACH_URL = "{server}/data/archive/projects/{project}/subjects/{subject}" \
             "/experiments/{session}/files/{filename}?" \
             "inbody=true" 

dcm_exts = ('dcm','img')

def fatal(message):
    print "ERROR:", message
    sys.exit(1)

def main():
    arguments = docopt(__doc__)
    server   = arguments['--server']
    project  = arguments['<project>']
    archive  = arguments['<archive>']
    verbose  = arguments['--verbose']
    username = arguments['--username']
    credfile = arguments['--credfile']

    if username: 
        password = getpass.getpass()
    else:
        lines = open(credfile).readlines()
        username = lines[0].strip()
        password = lines[1].strip()

    archivefile = os.path.basename(os.path.normpath(archive))
    scanid      = archivefile[:-len(dm.utils.get_extension(archivefile))]
    if not dm.scanid.is_scanid(scanid):
        fatal("{} is not a valid scan identifier".format(scanid))

    subject = scanid
    session = scanid
    auth = (username, password) 
    url_params = { 'server'  : server,
                   'project' : project,
                   'subject' : subject,
                   'session' : session }

    # Upload
    # https://wiki.xnat.org/pages/viewpage.action?pageId=5017279

    # create the subject
    if verbose: print "Creating subject {}".format(subject)
    r = requests.put(CREATE_URL.format(**url_params), auth=auth)
    
    r.raise_for_status()

    # upload the DICOM data
    # NOTE: If your project is not set to auto archive, then this will end up
    # in the prearchive
    if verbose: print "Uploading dicom data..."
    r = requests.post(UPLOAD_URL.format(**url_params), 
            auth=auth, 
            headers={'Content-Type' : 'application/zip'},
            data=open(archive))
            
    r.raise_for_status()

    # upload non-dicom stuff
    if verbose: print "Scanning for non-dicom data..."
    zf = zipfile.ZipFile(archive)

    # filter dirs
    files = zf.namelist()
    files = filter(lambda f: not f.endswith('/'), files)

    # filter files named like dicoms
    files = filter(lambda f: not is_named_like_a_dicom(f), files)

    # filter actual dicoms :D
    files = filter(lambda f: not is_dicom(io.BytesIO(zf.read(f))), files)

    if verbose: print "Uploading non-dicom data..."
    for f in files:
        r = None
        try:
            r = requests.post(ATTACH_URL.format(filename=f, **url_params),
                    data=zf.read(f),
                    auth=auth)

            r.raise_for_status() 
        except requests.exceptions.HTTPError, e:
            print "ERROR uploading file {}".format(f)
            print e

    if verbose: print "Done."

def is_named_like_a_dicom(path):
    return any(map(lambda x: path.lower().endswith(x), dcm_exts))

def is_dicom(fileobj):
    try:
        dcm.read_file(fileobj)
        return True
    except dcm.filereader.InvalidDicomError:
        return False

if __name__ == '__main__':
    try:
        main()
    except requests.exceptions.HTTPError, e:
        fatal(e)

# vim: ts=4 sw=4:
