#!/bin/bash
# -----------------------------------------------------------------------
# Version: 2014-01-09
# - rebuild and if correct install the package
#---------------------------------------------------
BENE="'Tutto bene!'";
BENENO="'No bene!'";
HABE_FERTIG="Ich habe fertig.";
NL="\n";
BASE_NAME=`basename $0`;
BASE_NAME_CUT=`basename $0 | cut -d '.' -f1`;
MESSAGE_TYPE="-I->";
exit_rc=0;
#---------------------------------------------------
DEB_PACKAGE="mapmbtiles_1.0.beta2_all.deb"
INSTALL_DIR="/usr/lib/mapmbtiles"
CMD_MAKEDEB="deploy/linux/makedeb"
if [ ! -f "${CMD_MAKEDEB}" ]
then
 exit_rc=1;
 MESSAGE_TYPE="-E->";
 echo -e "${NL}${MESSAGE_TYPE} ${BASE_NAME_CUT} rc=$exit_rc : 'dpkg' is not installed";
fi
CMD_DPKG=`which dpkg`
if [ -z "${CMD_DPKG}" ]
then
 exit_rc=2;
 MESSAGE_TYPE="-E->";
 echo -e "${NL}${MESSAGE_TYPE} ${BASE_NAME_CUT} rc=$exit_rc : 'dpkg' is not installed";
fi
#---------------------------------------------------
if [ "${exit_rc}" -eq 0 ]
then
 echo -e "${MESSAGE_TYPE} ${BASE_NAME_CUT} rc=$exit_rc : calling makedeb: ";
 ${CMD_MAKEDEB}
 exit_rc=$?
 if [ "${exit_rc}" -eq 0 ]
 then
  echo -e "${NL}${MESSAGE_TYPE} ${BASE_NAME_CUT} rc=$exit_rc calling dpkg: [${DEB_PACKAGE}] ";
  sudo ${CMD_DPKG} -i ${DEB_PACKAGE}
  exit_rc=$?
  if [ "${exit_rc}" -ne "0" ]
  then
   MESSAGE_TYPE="-E->";
   echo -e "${NL}${MESSAGE_TYPE} ${BASE_NAME_CUT} rc=$exit_rc : dpkg failed ";
  else
   CMD_GDAL2MBTILES=`which gdal2mbtiles`
   INFO_USER="${NL}to use in a python script: add the project to the 'PYTHONPATH' in '${HOME}/.bashrc' : "
   INFO_USER="${INFO_USER}${NL} with 'echo \"export PYTHONPATH=${INSTALL_DIR}:\$PYTHONPATH\" >> ${HOME}/.bashrc' "
   echo -e "${NL}${MESSAGE_TYPE} ${BASE_NAME_CUT} rc=$exit_rc installed in [${INSTALL_DIR}] [${CMD_GDAL2MBTILES}]${INFO_USER}";
  fi
 else
  MESSAGE_TYPE="-E->";
  echo -e "${NL}${MESSAGE_TYPE} ${BASE_NAME_CUT} rc=$exit_rc : makedeb failed ";
 fi
fi
#---------------------------------------------------
if [ "${exit_rc}" -eq "0" ]
then
 RC_TEXT=$BENE;
else
 RC_TEXT="$BENENO";
 MESSAGE_TYPE="-E->";
fi
#---------------------------------------------------
echo -e "${NL}${MESSAGE_TYPE} ${BASE_NAME_CUT} rc=$exit_rc [${RC_TEXT}] - ${HABE_FERTIG}";
exit $exit_rc;
#---------------------------------------------------
