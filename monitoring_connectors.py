import base64, json, ssl, urllib.request, urllib.error, ipaddress
from datetime import datetime

class ConnectorError(RuntimeError): pass

def _ctx(verify): return ssl.create_default_context() if verify else ssl._create_unverified_context()
def _auth(user,pw): return 'Basic '+base64.b64encode(f'{user}:{pw}'.encode()).decode()
def _request(ip,path,user,pw,verify=False,headers=None,method='GET',timeout=10):
    ipaddress.ip_address(ip)
    h={'Accept':'application/json','Authorization':_auth(user,pw)}
    if headers: h.update(headers)
    req=urllib.request.Request(f'https://{ip}{path}',headers=h,method=method)
    try:
        with urllib.request.urlopen(req,context=_ctx(verify),timeout=timeout) as r:
            raw=r.read().decode('utf-8','replace')
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        body=e.read().decode('utf-8','replace')[:300]
        raise ConnectorError(f'HTTP {e.code}: {body or e.reason}')
    except Exception as e: raise ConnectorError(str(e))

def _redfish_system(ip,user,pw,verify):
    root=_request(ip,'/redfish/v1/Systems/',user,pw,verify)
    members=root.get('Members') or []
    if not members: raise ConnectorError('Redfish Systems collection is empty')
    path=members[0].get('@odata.id')
    if not path: raise ConnectorError('Redfish system URI not returned')
    return _request(ip,path,user,pw,verify)

def probe_hpe_ilo(ip,user,pw,verify=False):
    d=_redfish_system(ip,user,pw,verify); st=d.get('Status') or {}
    return _result(st.get('Health') or st.get('State') or 'Online',d.get('Manufacturer') or 'HPE',d.get('Model'),d.get('SerialNumber'),d.get('BiosVersion'),{'power_state':d.get('PowerState'),'redfish_id':d.get('Id')})

def probe_dell_idrac(ip,user,pw,verify=False):
    d=_redfish_system(ip,user,pw,verify); st=d.get('Status') or {}
    return _result(st.get('Health') or st.get('State') or 'Online',d.get('Manufacturer') or 'Dell',d.get('Model'),d.get('SerialNumber') or d.get('SKU'),d.get('BiosVersion'),{'power_state':d.get('PowerState'),'redfish_id':d.get('Id')})

def probe_unity(ip,user,pw,verify=False):
    h={'X-EMC-REST-CLIENT':'true','Content-Type':'application/json'}
    d=_request(ip,'/api/types/system/instances?fields=name,model,serialNumber,health,softwareVersion',user,pw,verify,h)
    entries=d.get('entries') or []
    c=(entries[0].get('content') if entries else {}) or {}
    health=c.get('health') or {}; value=health.get('value') or health.get('name') or 'Online'
    return _result(str(value),'Dell EMC',c.get('model'),c.get('serialNumber'),c.get('softwareVersion'),{'name':c.get('name'),'health':health})

def probe_powerstore(ip,user,pw,verify=False):
    d=_request(ip,'/api/rest/appliance?select=id,name,model,service_tag,software_version,health',user,pw,verify)
    c=d[0] if isinstance(d,list) and d else (d or {})
    return _result(str(c.get('health') or 'Online'),'Dell',c.get('model'),c.get('service_tag'),c.get('software_version'),{'name':c.get('name'),'id':c.get('id')})

def probe_brocade_fos(ip,user,pw,verify=False):
    # FOS REST API (supported FOS releases). Endpoint returns switch identity/state.
    d=_request(ip,'/rest/running/brocade-fibrechannel-switch/fibrechannel-switch',user,pw,verify,{'Accept':'application/yang-data+json'})
    root=d.get('Response') or d
    arr=root.get('fibrechannel-switch') or root.get('brocade-fibrechannel-switch:fibrechannel-switch') or []
    c=arr[0] if isinstance(arr,list) and arr else (arr if isinstance(arr,dict) else {})
    status=c.get('operational-status') or c.get('switch-status') or 'Online'
    return _result(str(status),'Brocade',c.get('model') or c.get('switch-type'),c.get('chassis-user-friendly-name') or c.get('wwn'),c.get('firmware-version'),{'switch_name':c.get('user-friendly-name'),'wwn':c.get('name') or c.get('wwn')})

def _result(status,vendor,model,serial,firmware,details):
    return {'status':status or 'Unknown','vendor':vendor or '', 'model':model or '', 'serial_number':serial or '', 'firmware':firmware or '', 'last_error':'','last_seen':datetime.now().isoformat(),'details':details}

CONNECTORS={
 'HPE iLO (Redfish)':probe_hpe_ilo,
 'Dell iDRAC (Redfish)':probe_dell_idrac,
 'Dell EMC Unity (REST)':probe_unity,
 'Dell PowerStore (REST)':probe_powerstore,
 'Brocade FOS (REST)':probe_brocade_fos,
}
def probe(device,password):
    typ=device['device_type']; fn=CONNECTORS.get(typ)
    if not fn: raise ConnectorError(f'Unsupported connector: {typ}')
    return fn(device['management_ip'],device['username'],password,bool(device['verify_ssl']))
