//@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
// MIRcatSDK.h
//
// Copyright (c) 2013-2014.   All rights reserved.
// Daylight Solutions
// 15378 Avenue of Science, Suite 200
// San Diego, CA  92128
//@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@

#ifndef _MIRcatSDK_H_
#define _MIRcatSDK_H_
#include <stdint.h>

/* all the api macros */
#ifdef MIRCATSDK_EXPORTS
#define MIRCATSDK_DLL	__declspec(dllexport)
#else
#define MIRCATSDK_DLL	__declspec(dllimport)
#endif

/* Return Values */
#define MIRcatSDK_RET_SUCCESS                               ((uint32_t)0)

/* Comm and Transport Errors */
#define MIRcatSDK_RET_UNSUPPORTED_TRANSPORT                 ((uint32_t)1)

/* Initialization Errors */
#define MIRcatSDK_RET_INITIALIZATION_FAILURE                ((uint32_t)32)

/* Function return error codes */
#define MIRcatSDK_RET_ARMDISARM_FAILURE                     ((uint32_t)64)
#define MIRcatSDK_RET_STARTTUNE_FAILURE                     ((uint32_t)65)
#define MIRcatSDK_RET_INTERLOCKS_KEYSWITCH_NOTSET           ((uint32_t)66)
#define MIRcatSDK_RET_STOP_SCAN_FAILURE                     ((uint32_t)67)
#define MIRcatSDK_RET_PAUSE_SCAN_FAILURE                    ((uint32_t)68)
#define MIRcatSDK_RET_RESUME_SCAN_FAILURE                   ((uint32_t)69)
#define MIRcatSDK_RET_MANUAL_STEP_SCAN_FAILURE              ((uint32_t)70)
#define MIRcatSDK_RET_START_SWEEPSCAN_FAILURE               ((uint32_t)71)
#define MIRcatSDK_RET_START_STEPMEASURESCAN_FAILURE         ((uint32_t)72)
#define MIRcatSDK_RET_INDEX_OUTOFBOUNDS                     ((uint32_t)73)
#define MIRcatSDK_RET_START_MULTISPECTRALSCAN_FAILURE       ((uint32_t)74)
#define MIRcatSDK_RET_TOO_MANY_ELEMENTS                     ((uint32_t)75)
#define MIRcatSDK_RET_NOT_ENOUGH_ELEMENTS                   ((uint32_t)76)
#define MIRcatSDK_RET_BUFFER_TOO_SMALL                      ((uint32_t)77)
#define MIRcatSDK_RET_FAVORITE_NAME_NOTRECOGNIZED           ((uint32_t)78)
#define MIRcatSDK_RET_FAVORITE_RECALL_FAILURE               ((uint32_t)79)
#define MIRcatSDK_RET_WW_OUTOFTUNINGRANGE                   ((uint32_t)80)
#define MIRcatSDK_RET_NO_SCAN_INPROGRESS                    ((uint32_t)81)
#define MIRcatSDK_RET_EMISSION_ON_FAILURE                   ((uint32_t)82)
#define MIRcatSDK_RET_EMISSION_ALREADY_OFF                  ((uint32_t)83)
#define MIRcatSDK_RET_EMISSION_OFF_FAILURE                  ((uint32_t)84)
#define MIRcatSDK_RET_EMISSION_ALREADY_ON                   ((uint32_t)85)
#define MIRcatSDK_RET_PULSERATE_OUTOFRANGE                  ((uint32_t)86)
#define MIRcatSDK_RET_PULSEWIDTH_OUTOFRANGE                 ((uint32_t)87)
#define MIRcatSDK_RET_CURRENT_OUTOFRANGE                    ((uint32_t)88)
#define MIRcatSDK_RET_SAVE_SETTINGS_FAILURE                 ((uint32_t)89)
#define MIRcatSDK_RET_QCL_NUM_OUTOFRANGE                    ((uint32_t)90)
#define MIRcatSDK_RET_LASER_ALREADY_ARMED                   ((uint32_t)91)
#define MIRcatSDK_RET_LASER_ALREADY_DISARMED                ((uint32_t)92)
#define MIRcatSDK_RET_LASER_NOT_ARMED                       ((uint32_t)93)
#define MIRcatSDK_RET_LASER_NOT_TUNED                       ((uint32_t)94)
#define MIRcatSDK_RET_TECS_NOT_AT_SET_TEMPERATURE           ((uint32_t)95)
#define MIRcatSDK_RET_CW_NOT_ALLOWED_ON_QCL					((uint32_t)96)
#define MIRcatSDK_RET_INVALID_LASER_MODE					((uint32_t)97)
#define MIRcatSDK_RET_TEMPERATURE_OUT_OF_RANGE				((uint32_t)98)
#define MIRcatSDK_RET_LASER_POWER_OFF_ERROR				    ((uint32_t)99)
#define MIRcatSDK_RET_COMM_ERROR							((uint32_t)100)
#define MIRcatSDK_RET_NOT_INITIALIZED						((uint32_t)101)
#define MIRcatSDK_RET_ALREADY_CREATED						((uint32_t)102)
#define MIRcatSDK_RET_START_SWEEP_ADVANCED_SCAN_FAILURE		((uint32_t)103)
#define MIRcatSDK_RET_INJECT_PROC_TRIG_ERROR				((uint32_t)104)

/* Communication Parameters */
#define MIRcatSDK_COMM_SERIAL               ((uint8_t)1)
#define MIRcatSDK_COMM_UDP                  ((uint8_t)2)
#define MIRcatSDK_COMM_DEFAULT              MIRcatSDK_COMM_SERIAL

/* Serial port parameters */
/* Automatically find the device on the port */
#define MIRcatSDK_SERIAL_PORT_AUTO              ((uint16_t)0)
#define MIRcatSDK_SERIAL_BAUD_USE_DEFAULT       ((uint32_t)0)
#define MIRcatSDK_SERIAL_BAUD1					((uint16_t)115200)
#define MIRcatSDK_SERIAL_BAUD2					((uint16_t)921600)

/* Units */
/* Wave length Wave Number units */
#define MIRcatSDK_UNITS_MICRONS                 ((uint8_t)1)
#define MIRcatSDK_UNITS_CM1                     ((uint8_t)2)

/* Laser Modes */
#define MIRcatSDK_MODE_ERROR					((uint8_t)0)
#define MIRcatSDK_MODE_PULSED					((uint8_t)1)
#define MIRcatSDK_MODE_CW						((uint8_t)2)
#define MIRcatSDK_MODE_CW_MOD					((uint8_t)3)
#define MIRcatSDK_MODE_CW_MR					((uint8_t)6)	//currently not supported in firmware
#define MIRcatSDK_MODE_CW_MR_MOD				((uint8_t)7)	//currently not supported in firmware
#define MIRcatSDK_MODE_CW_FLTR1					((uint8_t)8)
#define MIRcatSDK_MODE_CW_FLTR2					((uint8_t)9)
#define MIRcatSDK_MODE_CW_FLTR1_MOD				((uint8_t)10)

/* Pulse Triggering Modes */
#define MIRcatSDK_PULSE_MODE_INTERNAL			((uint8_t)1)
#define MIRcatSDK_PULSE_MODE_EXTERNAL_TRIGGER	((uint8_t)2)
#define MIRcatSDK_PULSE_MODE_EXTERNAL_PASSTHRU	((uint8_t)3)
#define MIRcatSDK_PULSE_MODE_WAVELENGTH_TRIGGER ((uint8_t)4)

/* Process Triggering Modes */
#define MIRcatSDK_PROC_TRIG_MODE_INTERNAL		((uint8_t)1)
#define MIRcatSDK_PROC_TRIG_MODE_EXTERNAL		((uint8_t)2)
#define MIRcatSDK_PROC_TRIG_MODE_MANUAL			((uint8_t)3)

#ifdef __cplusplus
extern "C"
{
#endif

	/* COMMUNICATION FUNCTIONS */

	/** 
	<summary>Get Version of the API.</summary>
	<param name="papiVersionMajor">Major Version of MIRcat API.</param>
	<param name="papiVersionMinor">Minor Version of MIRcat API.</param>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetAPIVersion(uint16_t * papiVersionMajor, uint16_t * papiVersionMinor, uint16_t * papiVersionPatch);

	/** 
	<summary>Set the communications type.</summary>
	<see>MIRcatSDK_COMM_SERIAL</see>
	<see>MIRcatSDK_COMM_UDP</see>
	<see>MIRcatSDK_COMM_DEFAULT</see>
	<param name="commType">Communications Interface Type.</param>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_SetCommType(uint8_t commType);

	/** 
	<summary>Set serial port parameters.</summary>
	<see>MIRcatSDK_SERIAL_PORT_AUTO</see>
	<see>MIRcatSDK_SERIAL_BAUD_USE_DEFAULT</see>
	<param name="port">COM port number.</param>
	<param name="baud">Baud Rate.</param>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_SetSerialParams(uint16_t port, uint32_t baud);

	/**
	<summary>Creates new MIRcat object.  If a previous call has been made to MIRcatSDK_DeInitialize(),
	this function should be called before trying to call other MIRcatSDK functions.  </summary>
	*/	
	MIRCATSDK_DLL uint32_t MIRcatSDK_CreateMIRcatObject();

	/**
	<summary>Returns bool value indicating if MIRcat object has been created.  
	The object is destroyed following a call to MIRcatSDK_DeInitialize().  If it is
	destroyed it must be created before any SDK function calls will be valid.
	A call to MIRcatSDK_Initialize() will also create the object if it has been destroyed.
	</summary>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_IsMIRcatObjectCreated(bool * pbMIRcatObjectCreated);

	/** 
	<summary>Initialize the API.</summary>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_Initialize();


	/**
	<summary>Disconnect and clean up ports/memory associated with initializing the MIRcatSDK.
	A call to this function requires a call to MIRcatSDK_CreateMIRcatObject() or MIRcatSDK_Initialize()
	before any subsequent calls to any SDK functions.</summary>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_DeInitialize();

	/** INFORMATION FUNCTIONS */

	/** 
	<summary>Gets the model number of the MIRcat system.</summary>
	<param name="pszModelNumber">Pointer to character array that will contain model number after calling the function.  This array should be at least 24 bytes.</param>
	<param name="bSize">Size of pszModelNumber in bytes.</param>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetModelNumber(char * pszModelNumber, uint8_t bSize);

	/** 
	<summary>Gets the serial number of the MIRcat system.</summary>
	<param name="pszSerialNumber">Pointer to character array that will contain serial number after calling the function.  This array should be at least 24 bytes.</param>
	<param name="bSize">Size of pszSerialNumber in bytes.</param>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetSerialNumber(char * pszSerialNumber, uint8_t bSize);

	/** 
	<summary>Gets the tuning range of the MIRcat system.</summary>
	<param name="pfMinRange">Minimum wavelength of the MIRcat system.</param>
	<param name="pfMaxRange">Maximum wavelength of the MIRcat system.</param>
	<param name="pbUnits">Units for the min/max wavelength of the MIRcat system.</param>
	<see>MIRcatSDK_UNITS_MICRONS</see>
	<see>MIRcatSDK_UNITS_CM1</see>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetTuningRange(float * pfMinRange, float * pfMaxRange, uint8_t * pbUnits);

	/** 
	<summary>Gets the number of QCLs installed in the MIRcat system.</summary>
	<param name="pbNumQcls">Number of installed QCLs.</param>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetNumInstalledQcls(uint8_t * pbNumQcls);

	/** 
	<summary>Gets the tuning range of a particular QCL the MIRcat system.</summary>
	<param name="bQcl">QCL for which to get the tuning range, indexed 1-4.</param>
	<param name="pfMinRange">Minimum wavelength of the QCL.</param>
	<param name="pfMaxRange">Maximum wavelength of the QCL.</param>
	<param name="pbUnits">Units for the min/max wavelength of the MIRcat system.</param>
	<see>MIRcatSDK_UNITS_MICRONS</see>
	<see>MIRcatSDK_UNITS_CM1</see>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetQclTuningRange(uint8_t bQcl, float * pfMinRange, float * pfMaxRange, uint8_t * pbUnits);


	/* STATUS APIs */

	/** 
	<summary>Is there a valid connection to the laser?</summary>
	<param name="pbConnected">Bool value that indicates if the API is connected to the MIRcat system.</param>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_IsConnectedToLaser(bool * pbConnected);

	/** 
	<summary>Is the interlock set?</summary>
	<param name="pbSet">Bool value that indicates if the interlock circuit is closed.</param>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_IsInterlockedStatusSet(bool * pbSet);

	/** 
	<summary>Is the key switch in the ON position?</summary>
	<param name="pbSet">Bool value that indicates if the key switch is in the ON position.</param>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_IsKeySwitchStatusSet(bool * pbSet);

	/** 
	<summary>Is the laser emission on?</summary>
	<param name="pbIsOn">Bool value that indicates if the laser is currently emitting light.</param>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_IsEmissionOn(bool * pbIsOn);

	/** 
	<summary>Is the laser armed?</summary>
	<param name="pbIsArmed">Bool value that indicates if the laser is armed.</param>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_IsLaserArmed(bool * pbIsArmed);

	/** 
	<summary>Is there a system error?</summary>
	<param name="pbIsError">Bool value that indicates if there is a system error.</param>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_IsSystemError(bool * pbIsError);

	/** 
	<summary>Attempt to clear system error.  If the error cannot be cleared it is likely a serious system error.</summary>
	<param name="pbErrorCleared">Bool value that indicates the error could be cleared.  If </param>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_ClearSystemError(bool * pbErrorCleared );

	/** 
	<summary>Are all of the TECs at the set temperature?</summary>
	<param name="pbIsAtSetTemperature">Bool value that indicates if the TECs are at the set temperatures.</param>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_AreTECsAtSetTemperature(bool * pbIsAtSetTemperature);

	/** 
	<summary>Gets the system error word.</summary>
	<param name="pwErrorWord">16-bit error code.  See user's manual for a list of error codes.</param>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetSystemErrorWord(uint16_t * pwErrorWord);

	/** 
	<summary>Gets the wavelength display units specified in the laser settings.</summary>
	<param name="pbDisplayUnits">Display units for wavelength in the laser settings.</param>
	<see>MIRcatSDK_UNITS_MICRONS</see>
	<see>MIRcatSDK_UNITS_CM1</see>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetWWDisplayUnits(uint8_t * pbDisplayUnits );

	/** 
	<summary>Gets the status of the current scan/tune.</summary>
	<param name="pbIsScanInProgress">Bool value that indicates if the scan is in progress.</param>
	<param name="pbIsScanActive">Bool value that indicates if the scan is active.</param>
	<param name="pbIsScanPaused">Bool value that indicates if the scan is paused.</param>
	<param name="pwCurScanNum">Current scan number in repeated scan sequence.</param>
	<param name="pwCurrentScanPercent">Current scan percentage completed.</param>
	<param name="pfCurrentWW">Current wavelength of the laser.</param>
	<param name="pbUnits">Wavelength units.</param>
	<param name="pbIsTECInProgress">Bool value that indicates if the laser is waiting for a TEC to get to the target temperature before firing.</param>
	<param name="pbIsMotionInProgress">Bool value that indicates if a QCL is currently tuning.</param>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetScanStatus( bool * pbIsScanInProgress, bool * pbIsScanActive, bool * pbIsScanPaused, 
															uint16_t * pwCurScanNum, uint16_t * pwCurrentScanPercent, 
															float * pfCurrentWW, uint8_t * pbUnits, 
															bool * pbIsTECInProgress, bool * pbIsMotionInProgress);

	MIRCATSDK_DLL uint32_t MIRcatSDK_GetScanWaitingProcessTrigger( bool * bWaitProcTrig );

	/** 
	<summary>Gets the active QCL during a scan/tune.</summary>
	<param name="pbActiveQcl">The QCL that is active during this part of the scan/tune.</param>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetActiveQcl( uint8_t * pbActiveQcl );

	/* UTILITY FUNCTIONS */

	//Add function to convert from cm-1 to microns and vice-versa
	MIRCATSDK_DLL uint32_t MIRcatSDK_ConvertWW(float fWW, uint8_t bcurrentUnits, uint8_t bnewUnits, float * pfConvertedWW);

	/* ARM/DISARM Laser */

	/** 
	<summary>Arm the laser.</summary>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_ArmLaser();

	/** 
	<summary>Disarm the laser.</summary>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_DisarmLaser();

	/**
	<summary>Toggle the armed state of the laser based on the current state (i.e., if the laser is disarmed, this command will arm it and vice versa).</summary>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_ArmDisarmLaser();
    
	/* GENERAL SCAN OPERATIONS */

	/**
	<summary>Stops the current scan.</summary>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_StopScanInProgress();
	/**
	<summary>Pauses the current scan.  This function sends a pause command to the laser, but currently the laser does not support pausing of a scan.</summary>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_PauseScanInProgress();

	/**
	<summary>Resumes the current scan.  This function sends a resume command to the laser, but currently the laser does not support pausing of a scan, so will not resume.</summary>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_ResumeScanInProgress();

	/**
	<summary>Tells the laser to go to the next step in a Step and Measure or Multi-Spectral scan if the process trigger mode is set to Manual.</summary>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_ManualStepScanInProgress();

	/* TUNE APIs */
	
	/**
	<summary>Gets the actual tuned wavelength.  This can be used during a sweep or tune to indicate when target is reached</summary>
	<param name="pfActualWW">The actual wavelength the laser is currently tuned to.</param>
	<param name="pbUnits">The wavelength units for the tuning.</param>
	<param name="pbLightValid">Indicates if laser light is valid (tuned and emitting).</param>
	<see>MIRcatSDK_UNITS_MICRONS</see>
	<see>MIRcatSDK_UNITS_CM1</see>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetActualWW(float * pfActualWW, uint8_t * pbUnits, bool * pbLightValid);
	
	/**
	<summary>Gets the currently tuned target wavelength.</summary>
	<param name="pfTuneWW">The wavelength the laser is currently tuned to.</param>
	<param name="pbUnits">The wavelength units for the tuning.</param>
	<param name="pbPreferredQcl">The preferred QCL as specified in the last TuneToWW command indexed 1-4.  A value of 0 indicates no preferred QCL.</param>
	<see>MIRcatSDK_UNITS_MICRONS</see>
	<see>MIRcatSDK_UNITS_CM1</see>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetTuneWW(float * pfTuneWW, uint8_t * pbUnits, uint8_t * pbPreferredQcl);
	
	/**
	<summary>Tune the laser to the specified wavelength with a preferred QCL.</summary>
	<param name="fTuneWW">The target wavelength to tune the laser to.</param>
	<param name="bUnits">The wavelength units for tuning the laser.</param>
	<param name="bPreferredQcl">The preferred QCL for this tune command indexed 1-4.  A value of 0 indicates no preferred QCL.</param>
	<see>MIRcatSDK_UNITS_MICRONS</see>
	<see>MIRcatSDK_UNITS_CM1</see>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_TuneToWW(float fTuneWW, uint8_t bUnits, uint8_t bPreferredQcl);
	
	/**
	<summary>Is the laser tuned?</summary>
	<param name="pbIsTuned">Bool value that indicates if the laser is currently tuned.</param>	
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_IsTuned(bool * pbIsTuned);

	/**
	<summary>Cancel the current single tune.  If the laser is tuned in single tune mode, this command must be sent before performing a scan.</summary>	
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_CancelManualTuneMode();

	/**
	<summary>Turns laser emission on.  Laser must have been tuned to a wavelength prior to sending this command.</summary>	
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_TurnEmissionOn();

	/**
	<summary>Turns laser emission off.  If the laser emission is already off, this will return the MIRcatSDK_RET_EMISSION_ALREADY_OFF code.</summary>	
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_TurnEmissionOff();
    
    
	/* SWEEP APIs */

	/**
	<summary>Gets the sweep start wavelength from the last sweep scan.</summary>
	<param name="pfStartWW">Start wavelength of the last scan.</param>	
	<param name="pbUnits">Wavelength units.</param>	
	<see>MIRcatSDK_UNITS_MICRONS</see>
	<see>MIRcatSDK_UNITS_CM1</see>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetSweepStartWW(float * pfStartWW, uint8_t * pbUnits);

	/**
	<summary>Gets the sweep stop wavelength from the last sweep scan.</summary>
	<param name="pfStopWW">Stop wavelength of the last scan.</param>	
	<param name="pbUnits">Wavelength units.</param>	
	<see>MIRcatSDK_UNITS_MICRONS</see>
	<see>MIRcatSDK_UNITS_CM1</see>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetSweepStopWW(float * pfStopWW, uint8_t * pbUnits);

	/**
	<summary>Gets the sweep speed in the indicated units per second from the last sweep scan.</summary>
	<param name="pfScanSpeed">Scan speed in units per second.</param>	
	<param name="pbUnits">Wavelength units.</param>	
	<see>MIRcatSDK_UNITS_MICRONS</see>
	<see>MIRcatSDK_UNITS_CM1</see>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetSweepScanSpeed(float * pfScanSpeed, uint8_t * pbUnits);

	/**
	<summary>Gets the number of iterations to be performed for this scan.</summary>
	<param name="pwNumScans">Number of scan iterations to be performed.  Note: A bi-directional scan will count the scan up and scan down as a single scan.</param>	
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetSweepNumScans(uint16_t * pwNumScans);

	/**
	<summary>Is this scan bi-directional?</summary>
	<param name="pbIsBidirectional">Bool value indicating if this scan is bi-directional.</param>	
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_IsSweepBidirectional(bool * pbIsBidirectional);

	/**
	<summary>Starts a sweep scan with the specified parameters.</summary>
	<param name="fStartWW">Start wavelength for this scan.</param>	
	<param name="fStopWW">Stop wavelength for this scan.</param>	
	<param name="fScanSpeed">Scan speed in specified units per second.</param>	
	<param name="bUnits">Wavelength units for this scan.</param>	
	<param name="wNumScans">Number of iterations of this scan to perform.</param>	
	<param name="bIsBiDirectional">Bool value indicating if this scan is bi-directional.</param>	
	<param name="u8PreferredQcl">The preferred QCL for this sweep scan command indexed 1-4.  A value of 0 indicates no preferred QCL.  If there is a preferred QCL, the scan will switch to this QCL as soon as possible and stay on this QCL as long as possible.</param>	
	<see>MIRcatSDK_UNITS_MICRONS</see>
	<see>MIRcatSDK_UNITS_CM1</see>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_StartSweepScan(float fStartWW, float fStopWW, float fScanSpeed, 
															uint8_t bUnits, uint16_t wNumScans, bool bIsBiDirectional, uint8_t u8PreferredQcl);
    

	/* STEP & MEASURE APIs */

	/**
	<summary>Gets the Step and Measure start wavelength from the last Step and Measure scan.</summary>
	<param name="pfStartWW">Start wavelength of the last scan.</param>	
	<param name="pbUnits">Wavelength units.</param>	
	<see>MIRcatSDK_UNITS_MICRONS</see>
	<see>MIRcatSDK_UNITS_CM1</see>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetStepMeasureStartWW(float * pfStartWW, uint8_t * pbUnits);

	/**
	<summary>Gets the Step and Measure stop wavelength from the last Step and Measure scan.</summary>
	<param name="pfStopWW">Stop wavelength of the last scan.</param>	
	<param name="pbUnits">Wavelength units.</param>	
	<see>MIRcatSDK_UNITS_MICRONS</see>
	<see>MIRcatSDK_UNITS_CM1</see>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetStepMeasureStopWW(float * pfStopWW, uint8_t * pbUnits);

	/**
	<summary>Gets the Step and Measure step size from the last Step and Measure scan.</summary>
	<param name="pfStepSize">Step size in the specified units.</param>	
	<param name="pbUnits">Wavelength units.</param>	
	<see>MIRcatSDK_UNITS_MICRONS</see>
	<see>MIRcatSDK_UNITS_CM1</see>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetStepMeasureStepSizeWW(float * pfStepSize, uint8_t * pbUnits);

	/**
	<summary>Gets the Step and Measure step size from the last Step and Measure scan.</summary>
	<param name="pfStepSize">Step size in the specified units.</param>	
	<param name="pbUnits">Wavelength units.</param>	
	<see>MIRcatSDK_UNITS_MICRONS</see>
	<see>MIRcatSDK_UNITS_CM1</see>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetStepMeasureNumScans(uint16_t * pwNumScans);    

	/**
	<summary>Starts a Step and Measure scan with the specified parameters.</summary>
	<param name="fStart">Start wavelength in the specified units.</param>	
	<param name="fStop">Stop wavelength in the specified units.</param>
	<param name="fStepSize">Step size in the specified units.</param>	
	<param name="bUnits">Wavelength units.</param>
	<param name="wNumScans">Number of iterations to be performed for this scan.</param>	
	<see>MIRcatSDK_UNITS_MICRONS</see>
	<see>MIRcatSDK_UNITS_CM1</see>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_StartStepMeasureModeScan(float fStart, float fStop, float fStepSize, 
																		uint8_t bUnits, uint16_t wNumScans );

	/* MULTI-SPECTRAL APIs */

	/**
	<summary>Gets the number of elements in the last Multi-Spectral scan.</summary>
	<param name="pbNumElements">Number of elements in the Multi-Spectral scan.</param>	
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetNumMultiSpectralElements(uint8_t * pbNumElements);

	/**
	<summary>Gets the parameters for the specified element in a Multi-Spectral scan.</summary>
	<param name="bIndex">Element index.</param>	
	<param name="pfScanWW">Element wavelength.</param>	
	<param name="pdwDwellTime">Element dwell time.</param>	
	<param name="pdwOffTime">Element off time.</param>	
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetMultiSpectralElement(uint8_t bIndex, float * pfScanWW, uint32_t * pdwDwellTime, uint32_t * pdwOffTime);

	/**
	<summary>Gets the wavelength units for the last Multi-Spectral scan.</summary>
	<param name="pbUnits">Wavelength units for the Multi-Spectral scan.</param>	
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetMultiSpectralWWUnits(uint8_t * pbUnits);

	/**
	<summary>Gets the number of iterations for the last Multi-Spectral scan.</summary>
	<param name="pwNumScans">Number of scan iterations.</param>	
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetMultiSpectralNumScans(uint16_t * pwNumScans);  

	/**
	<summary>Sets the number of elements for a Multi-Spectral scan.</summary>
	<param name="bNumElements">Number of elements in a Multi-Spectral scan.</param>	
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_SetNumMultiSpectralElements(uint8_t bNumElements);

	/**
	<summary>Adds a Multi-Spectral scan element to the end of the element list.</summary>
	<param name="fScanWW">Element wavelength.</param>	
	<param name="bUnits">Element wavelength units.</param>	
	<param name="dwDwellTime">Element dwell time.</param>	
	<param name="dwOffTime">Element off time.</param>	
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_AddMultiSpectralElement(float fScanWW, uint8_t bUnits, uint32_t dwDwellTime, uint32_t dwOffTime);

	/**
	<summary>Starts a Multi-Spectral scan with the specified number of iterations.  The elements for this scan must have been setup previously.</summary>
	<param name="wNumScans">Number of iterations for this Multi-Spectral scan.</param>	
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_StartMultiSpectralModeScan(uint16_t wNumScans);

	/* FAVORITES APIs */

	/**
	<summary>Gets the number of user favorites that have been saved.</summary>
	<param name="pbNumFavorites">Number of favorites saved in the laser memory.</param>	
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetNumFavorites(uint8_t * pbNumFavorites);

	/**
	<summary>Gets the name of the favorite at the specified index.</summary>
	<param name="bIndex">Index of the favorite.</param>	
	<param name="pszFavoriteName">Name of the favorite.  This character array should be 32 bytes .</param>	
	<param name="bSize">Length in bytes of the favorite name.</param>	
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetFavoriteName(uint8_t bIndex, char * pszFavoriteName, uint8_t bSize);

	/**
	<summary>Recalls the favorite with the given name.</summary>
	<param name="pszFavoriteName">Name of the favorite to recall.</param>	
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_RecallFavorite(char * pszFavoriteName);

	/* SETTINGS APIs */

	/* All QCLs are indexed starting from 1 */

	/**
	<summary>Gets the pulse rate of the specified QCL in Hz.</summary>
	<param name="bQcl">QCL number indexed from 1.</param>	
	<param name="pfPulseRateInHz">Pulse Rate in Hz.</param>	
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetQCLPulseRate(uint8_t bQcl, float * pfPulseRateInHz);

	/**
	<summary>Gets the pulse width of the specified QCL in ns.</summary>
	<param name="bQcl">QCL number indexed from 1.</param>	
	<param name="pfPulseWidthInNanoSec">Pulse Width in ns.</param>	
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetQCLPulseWidth(uint8_t bQcl, float * pfPulseWidthInNanoSec);
	
	/**
	<summary>Gets the current setting of the specified QCL in mA.</summary>
	<param name="bQcl">QCL number indexed from 1.</param>	
	<param name="pfCurrentInMilliAmps">Current setting in mA.</param>	
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetQCLCurrent(uint8_t bQcl, float * pfCurrentInMilliAmps);	

	/**
	<summary>Set the operating parameters for the specified QCL.</summary>
	<param name="bQcl">QCL number indexed from 1.</param>	
	<param name="fPulseRateInHz">Pulse rate in Hz.</param>	
	<param name="fPulseWidthInNanoSec">Pulse width in ns.</param>
	<param name="fCurrentInMilliAmps">Current in mA.</param>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_SetQCLParams(uint8_t bQcl, float fPulseRateInHz, float fPulseWidthInNanoSec, float fCurrentInMilliAmps);

	/**
	<summary>Gets the pulse limits for the  specified QCL.</summary>
	<param name="bQcl">QCL number indexed from 1-4.</param>	
	<param name="pfpfPulseRateMaxInHz">Maximum pulse rate in Hz.</param>	
	<param name="pfPulseWidthMaxInNanoSec">Maximum pulse width in ns.</param>
	<param name="pfDutyCycleMax">Maximum pulsed duty cycle.</param>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetQCLPulseLimits(uint8_t bQcl, float * pfpfPulseRateMaxInHz, float * pfPulseWidthMaxInNanoSec, float * pfDutyCycleMax);

	/**
	<summary>Gets the max pulsed current setting of the specified QCL in mA.</summary>
	<param name="bQcl">QCL number indexed from 1-4.</param>	
	<param name="pfCurrentInMilliAmps">Maximum QCL current in mA.</param>	
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetQCLMaxPulsedCurrent(uint8_t bQcl, uint16_t * pfCurrentInMilliAmps);	

	/**
	<summary>Gets the max CW current setting of the specified QCL in mA.</summary>
	<param name="bQcl">QCL number indexed from 1-4.</param>	
	<param name="pfCurrentInMilliAmps">Maximum QCL current in mA.</param>	
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetQCLMaxCwCurrent(uint8_t bQcl, uint16_t * pfCurrentInMilliAmps);

	/**
	<summary>Gets the status of CW being supported for this QCL.</summary>
	<param name="bQcl">QCL number indexed from 1-4.</param>	
	<param name="pbCwAllowed">Bool value that indicates if CW is supported on this channel.</param>	
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_isCwAllowed(uint8_t bQcl, bool * pbCwAllowed);

	/**
	<summary>Gets the status of CW filters being supported for this QCL.</summary>
	<param name="bQcl">QCL number indexed from 1-4.</param>	
	<param name="pbCwAllowed">Bool value that indicates if CW filters are installed on this channel.</param>	
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_areCwFiltersInstalled(uint8_t bQcl, bool * pbFiltersInstalled);

	/**
	<summary>Gets the TEC current for the specified channel.</summary>
	<param name="bQcl">TEC number indexed from 1-4.</param>	
	<param name="pfCurrentInMilliAmps">TEC current in mA.</param>	
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetTecCurrent(uint8_t bTec, uint16_t * pfCurrentInMilliAmps);

	/**
	<summary>Gets the QCL temperature for the specified channel.</summary>
	<param name="bQcl">QCL number indexed from 1-4.</param>	
	<param name="pfQclTemperature">QCL temperature in degrees C.</param>	
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetQCLTemperature(uint8_t bQcl, float * pfQclTemperature);

	/**
	<summary>Gets the QCL operating mode for the specified channel.</summary>
	<param name="bQcl">QCL number indexed from 1-4.</param>	
	<param name="pbMode">QCL operating mode.</param>		
	<see>MIRcatSDK_MODE_ERROR</see>
	<see>MIRcatSDK_MODE_PULSED</see>
	<see>MIRcatSDK_MODE_CW</see>
	<see>MIRcatSDK_MODE_CW_MOD</see>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetQCLOperatingMode(uint8_t bQcl, uint8_t * pbMode);
	
	/**
	<summary>Gets the QCL set temperature for the specified channel in degrees C.</summary>
	<param name="bQcl">QCL number indexed from 1-4.</param>	
	<param name="pfQclSetTemperature">QCL set temperature.</param>	
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetQclSetTemperature(uint8_t bQcl, float * pfQclSetTemperature);

	/**
	<summary>Gets the QCL temperature range for the specified channel in degrees C.</summary>
	<param name="bQcl">QCL number indexed from 1-4.</param>	
	<param name="pfQclNominalTemperature">QCL nominal factory temperature.</param>
	<param name="pfQclMinTemperature">QCL minimum temperature.</param>
	<param name="pfQclMaxTemperature">QCL maximum temperature.</param>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetQCLTemperatureRange(uint8_t bQcl, float * pfQclNominalTemperature, float * pfQclMinTemperature, float * pfQclMaxTemperature);

	/**
	<summary>Set all of the operating parameters for the specified QCL.</summary>
	<param name="bQcl">QCL number indexed from 1.</param>	
	<param name="fPulseRateInHz">Pulse rate in Hz.</param>	
	<param name="fPulseWidthInNanoSec">Pulse width in ns.</param>
	<param name="fCurrentInMilliAmps">Current in mA.</param>
	<param name="fTemperature">Temperature in degrees Celsius.</param>
	<param name="u8laserMode">Laser Mode (Pulsed, CW, or CW+Mod).</param>	
	<see>MIRcatSDK_MODE_PULSED</see>
	<see>MIRcatSDK_MODE_CW</see>
	<see>MIRcatSDK_MODE_CW_MOD</see>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_SetAllQclParams(uint8_t bQcl, float fPulseRate, float fPulseWidth, float fCurrentInMilliAmps, float fTemperature, uint8_t u8laserMode);

	/**
	<summary>Set all of the operating parameters for the specified QCL.</summary>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_PowerOffSystem( void );

	/*********************************************************************************************************
	 *	Adding new functions below
	 *********************************************************************************************************/
		
	/**
	<summary>Gets the current wavelength trigger parameters in the laser settings.</summary>
	<param name="pbPulseMode">Pulse Triggering Mode</param>	
	<param name="pfWlTrigStart">Wavelength Trigger Start Wavelength</param>	
	<param name="pfWlTrigStop">Wavelength Trigger Stop Wavelength</param>	
	<param name="pfWlTrigInterval">Wavelength Trigger Interval.</param>	
	<param name="units">Wavelength Units for trigger parameters</param>	
	<see>MIRcatSDK_PULSE_MODE_INTERNAL</see>
	<see>MIRcatSDK_PULSE_MODE_EXTERNAL_TRIGGER</see>
	<see>MIRcatSDK_PULSE_MODE_EXTERNAL_PASSTHRU</see>
	<see>MIRcatSDK_PULSE_MODE_WAVELENGTH_TRIGGER</see>
	<see>MIRcatSDK_PROC_TRIG_MODE_INTERNAL</see>
	<see>MIRcatSDK_PROC_TRIG_MODE_EXTERNAL</see>
	<see>MIRcatSDK_PROC_TRIG_MODE_MANUAL</see>
	<see>MIRcatSDK_UNITS_MICRONS</see>
	<see>MIRcatSDK_UNITS_CM1</see>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetWlTrigParams( uint8_t * pbPulseMode, uint8_t * pbProcTrigMode, float * pfWlTrigStart, float * pfWlTrigStop, float * pfWlTrigInterval, uint8_t * pbUnits, uint32_t * pDwellTime, uint32_t * pAfterOffTime );

	/**
	<summary>Sets the current wavelength trigger parameters in the laser settings.</summary>
	<param name="pbPulseMode">Pulse Triggering Mode</param>	
	<param name="pfWlTrigStart">Wavelength Trigger Start Wavelength</param>	
	<param name="pfWlTrigStop">Wavelength Trigger Stop Wavelength</param>	
	<param name="pfWlTrigInterval">Wavelength Trigger Interval.</param>	
	<param name="units">Wavelength Units for trigger parameters</param>	
	<see>MIRcatSDK_PULSE_MODE_INTERNAL</see>
	<see>MIRcatSDK_PULSE_MODE_EXTERNAL_TRIGGER</see>
	<see>MIRcatSDK_PULSE_MODE_EXTERNAL_PASSTHRU</see>
	<see>MIRcatSDK_PULSE_MODE_WAVELENGTH_TRIGGER</see>
	<see>MIRcatSDK_PROC_TRIG_MODE_INTERNAL</see>
	<see>MIRcatSDK_PROC_TRIG_MODE_EXTERNAL</see>
	<see>MIRcatSDK_PROC_TRIG_MODE_MANUAL</see>
	<see>MIRcatSDK_UNITS_MICRONS</see>
	<see>MIRcatSDK_UNITS_CM1</see>
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_SetWlTrigParams( uint8_t pbPulseMode, uint8_t pbProcTrigMode, float pfWlTrigStart, float pfWlTrigStop, float pfWlTrigInterval, uint8_t pbUnits, uint32_t pDwellTime, uint32_t pAfterOffTime );
	
	/**
	<summary>Gets System Temperatures.</summary>
	<param name="pfBenchTemp1">Bench Temperature Sensor 1 (degrees C)</param>	
	<param name="pfBenchTemp2">Bench Temperature Sensor 2 (degrees C)</param>	
	<param name="pfPcbTemp">PCB Temperature Sensor (degrees C)</param>		
	<returns>Error code.</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetSystemTemperatures( float * pfBenchTemp1, float * pfBenchTemp2, float * pfPcbTemp );


	MIRCATSDK_DLL uint32_t MIRcatSDK_ReadWriteAdvancedSweepParams( bool fWrite );
	MIRCATSDK_DLL uint32_t MIRcatSDK_SetAdvancedSweepParams( uint8_t pbUnits, float pfStartWave, float pfStopWave, float pfSpeed,
																	 uint16_t psNumScans, bool pbBidirectional );

	MIRCATSDK_DLL uint32_t MIRcatSDK_GetAdvancedSweepParams( uint8_t *pbUnits, float *pfStartWave, float *pfStopWave, float *pfSpeed,
																	 uint16_t *psNumScans, bool *pbBidirectional );

	MIRCATSDK_DLL uint32_t MIRcatSDK_SetAdvancedSweepChanParams( uint8_t bQcl, float chStartWave, float chStopWave, bool useChannel );
	MIRCATSDK_DLL uint32_t MIRcatSDK_GetAdvancedSweepChanParams( uint8_t bQcl, float *chStartWave, float *chStopWave, bool *useChannel );
	MIRCATSDK_DLL uint32_t MIRcatSDK_StartSweepAdvancedScan( void );

	/**
	<summary>Inject a manual process trigger into the system for scans when in manual process trigger mode.</summary>
	<returns>Error code. (MIRcatSDK_RET_INJECT_PROC_TRIG_ERROR) or (MIRcatSDK_RET_SUCCESS)</returns>
	*/
	MIRCATSDK_DLL uint32_t MIRcatSDK_InjectProcessTrigger( void );

	

	/*********************************************************************************************************
	 *	End of New Functions
	 *********************************************************************************************************/


#ifdef __cplusplus
}
#endif

#endif // _MIRcatSDK_H_
