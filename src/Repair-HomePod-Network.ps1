[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Program,
    [Parameter(Mandatory=$true)][string]$DataDir,
    [Parameter(Mandatory=$true)][string]$Request
)
$ErrorActionPreference='Stop'
$result=@{request=$Request;ok=$false}
try{
    $identity=[Security.Principal.WindowsIdentity]::GetCurrent()
    $principal=[Security.Principal.WindowsPrincipal]::new($identity)
    if(!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){
        throw 'Administrator permission is required to add this application firewall rule.'
    }
    $exePath=(Resolve-Path -LiteralPath $Program).ProviderPath
    if((Split-Path -Leaf $exePath) -ne 'BedroomAudio.exe'){
        throw 'The firewall rule must target BedroomAudio.exe.'
    }
    $devices=Get-Content -LiteralPath (Join-Path $DataDir 'devices.json') -Raw -Encoding utf8 | ConvertFrom-Json
    $config=Get-Content -LiteralPath (Join-Path $DataDir 'config.json') -Raw -Encoding utf8 | ConvertFrom-Json
    $allowed=@($config.devices | ForEach-Object {
        $deviceId=([string]$_.id).Replace(':','').ToUpperInvariant()
        if($deviceId -notmatch '^[0-9A-F]{12}$'){throw 'Invalid configured receiver ID.'}
        $deviceId
    } | Select-Object -Unique)
    if($allowed.Count -ne 2){throw 'Exactly two configured receivers are required.'}
    $addresses=@($devices | Where-Object {$_.id -in $allowed -and $_.reachable} | ForEach-Object {
        $address=[System.Net.IPAddress]::Parse($_.address)
        if($address.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork){throw 'Only IPv4 HomePod addresses are supported.'}
        $bytes=$address.GetAddressBytes()
        if(!(($bytes[0] -eq 10) -or ($bytes[0] -eq 192 -and $bytes[1] -eq 168) -or
             ($bytes[0] -eq 172 -and $bytes[1] -ge 16 -and $bytes[1] -le 31))){throw 'HomePod must have a private LAN address.'}
        $address.IPAddressToString
    } | Select-Object -Unique)
    if($addresses.Count -eq 0){throw 'No known HomePod addresses were found. Refresh devices first.'}
    $options=@{
        Name='BedroomAudio-HomePod-UDP';Direction='Inbound';Action='Allow';Enabled='True';
        Profile='Any';Program=$exePath;Protocol='UDP';RemoteAddress=$addresses;
        Description='AirPlay clock and audio control from the configured HomePod private addresses only.'
    }
    $existing=Get-NetFirewallRule -Name $options.Name -ErrorAction SilentlyContinue
    if($existing){Set-NetFirewallRule @options | Out-Null}
    else{New-NetFirewallRule @options -DisplayName 'Bedroom Audio - HomePod UDP' -Group 'Bedroom Audio' | Out-Null}
    $active=Get-NetFirewallRule -Name $options.Name -PolicyStore ActiveStore
    if($active.Enabled -ne 'True' -or $active.Action -ne 'Allow'){throw 'The rule is not active. Windows policy may be preventing local rules.'}
    $result.ok=$true;$result.program=$exePath;$result.remote_addresses=$addresses;$result.rule=$options.Name
}catch{
    $result.error=$_.Exception.Message
}finally{
    $result | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $DataDir 'network-repair.json') -Encoding utf8
}
if(!$result.ok){exit 1}
