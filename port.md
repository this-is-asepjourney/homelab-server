### HOST INFORMATION

 Static hostname: fa
       Icon name: computer-desktop
         Chassis: desktop 🖥️
      Machine ID: 9e4227ad163b4048b41efc7bc0732293
         Boot ID: a44a66da033f4a35832190574ce57d7d
Operating System: Ubuntu 24.04.5 LTS
          Kernel: Linux 6.8.0-147-generic
    Architecture: x86-64
 Hardware Vendor: Dell Inc.
  Hardware Model: OptiPlex 7050
Firmware Version: 1.11.0
   Firmware Date: Thu 2018-11-01
    Firmware Age: 8y 3d

### NETWORK ADDRESSES

lo               UNKNOWN        127.0.0.1/8 ::1/128
enp0s31f6        UP             192.168.25.101/24 fe80::16b3:1fff:fe0f:418d/64
tailscale0       UNKNOWN        100.106.63.90/32 fd7a:115c:a1e0::bc4e:3f5b/128 fe80::5765:775e:2589:aa5d/64
br-fb0a5b1af4ce  UP             172.19.0.1/16 fe80::58fa:54ff:fe9b:91a7/64
br-fcca42808cfb  UP             172.18.0.1/16 fe80::4c1:9fff:fe5e:8191/64
br-0edf946f444a  UP             172.24.0.1/16 fe80::88a9:5dff:fe93:73/64
br-2db2c4938c22  DOWN           172.25.0.1/16
br-430ea2f6adc4  UP             172.20.0.1/16 fe80::340f:4cff:fee6:9c63/64
docker0          DOWN           172.17.0.1/16 fe80::d8ca:aaff:fec1:c23/64
br-708a787ad94a  UP             172.22.0.1/16 fdc7:7a99:3662::1/64 fe80::ec8e:f9ff:fe73:e6cc/64
br-c08065816af3  UP             172.21.0.1/16 fe80::a078:c1ff:fea0:e463/64
docker_gwbridge  DOWN           172.23.0.1/16
vethb50d195@if2  UP             fe80::48c2:7aff:fe71:9ff7/64
vethf1ef3be@if2  UP             fe80::d061:26ff:fe52:b349/64
vetha63cefa@if2  UP             fe80::d4c6:21ff:fe97:e9d6/64
veth4361eab@if2  UP             fe80::4048:38ff:fed4:67db/64
veth2d98355@if2  UP             fe80::c0f1:8bff:fee2:ccbc/64
veth9054632@if2  UP             fe80::1819:67ff:fe75:a6e1/64
vethc6058c6@if2  UP             fe80::1c10:97ff:fec1:f31d/64
vetha9ae6f2@if2  UP             fe80::dc76:b2ff:fee1:cc3d/64
veth4523372@if2  UP             fe80::9840:90ff:feea:90c4/64
veth63b34b4@if2  UP             fe80::10bd:73ff:fef4:9dc7/64
vethb3afbff@if2  UP             fe80::a87d:7fff:fe27:d7b2/64
vxlan.calico     UNKNOWN        10.1.29.64/32
br-acb99e07662a  UP             172.26.0.1/16 fe80::1856:18ff:fe0b:a91c/64
veth6c4aca7@if2  UP             fe80::acf1:f7ff:fe14:231a/64
br-c1ea445ac3d9  UP             172.28.0.1/16 fe80::c29:8eff:fe92:223e/64
br-30428276c7b1  UP             172.27.0.1/16 fe80::548e:c2ff:fe76:5600/64
vethe35f5ec@if2  UP             fe80::6812:eff:fe05:1cd0/64
veth5690404@if2  UP             fe80::441c:34ff:fe1b:32d/64
vethc87e6d0@if2  UP             fe80::8486:87ff:fe54:3c4/64
vethc71e102@if2  UP             fe80::74f8:31ff:fe1d:dde4/64
veth5975f4d@if2  UP             fe80::9826:b9ff:feba:f731/64
br-de48b9a22c46  DOWN           172.29.0.1/16
calid7174edd940@if2 UP             fe80::ecee:eeff:feee:eeee/64
cali2243222ac53@if2 UP             fe80::ecee:eeff:feee:eeee/64

fa@fa:~$ echo "=========================================="
echo " AUDIT PORT SERVER - UBUNTU HOMELAB"
echo "=========================================="

echo
echo "===== 1. PORT LISTENING ====="
sudo ss -lntup

echo
echo "===== 2. PORT TCP LISTENING ====="
sudo ss -lntp

echo
echo "===== 3. PORT UDP LISTENING ====="
sudo ss -lnup
==========================================

AUDIT PORT SERVER - UBUNTU HOMELAB
==========================================

===== 1. PORT LISTENING =====
Netid    State      Recv-Q     Send-Q                                  Local Address:Port          Peer Address:Port    Process
udp      UNCONN     0          0                                             0.0.0.0:41641              0.0.0.0:*users:(("tailscaled",pid=1188,fd=19))
udp      UNCONN     0          0                                             0.0.0.0:4789               0.0.0.0:*
udp      UNCONN     0          0                                          127.0.0.54:53                 0.0.0.0:*users:(("systemd-resolve",pid=770,fd=16))
udp      UNCONN     0          0                                       127.0.0.53%lo:53                 0.0.0.0:*        users:(("systemd-resolve",pid=770,fd=14))
udp      UNCONN     0          0                                                [::]:41641                 [::]:*users:(("tailscaled",pid=1188,fd=18))
udp      UNCONN     0          0                                                   *:7946                     *:*        users:(("dockerd",pid=1510,fd=118))
tcp      LISTEN     0          4096                                        127.0.0.1:37941              0.0.0.0:*        users:(("containerd",pid=4123118,fd=13))
tcp      LISTEN     0          4096                                    100.106.63.90:3306               0.0.0.0:*        users:(("docker-proxy",pid=4652,fd=8))
tcp      LISTEN     0          4096                                        127.0.0.1:1338               0.0.0.0:*users:(("containerd",pid=4123118,fd=3))
tcp      LISTEN     0          4096                                    100.106.63.90:5432               0.0.0.0:*        users:(("docker-proxy",pid=5200,fd=8))
tcp      LISTEN     0          4096                         100.106.63.90%tailscale0:34098              0.0.0.0:*users:(("tailscaled",pid=1188,fd=22))
tcp      LISTEN     0          4096                                          0.0.0.0:22                 0.0.0.0:*        users:(("sshd",pid=240904,fd=3),("systemd",pid=1,fd=211))
tcp      LISTEN     0          4096                                   192.168.25.101:5001               0.0.0.0:*users:(("docker-proxy",pid=5253,fd=8))
tcp      LISTEN     0          4096                                          0.0.0.0:3005               0.0.0.0:*        users:(("docker-proxy",pid=3514025,fd=8))
tcp      LISTEN     0          4096                                   192.168.25.101:3002               0.0.0.0:*users:(("docker-proxy",pid=4516,fd=8))
tcp      LISTEN     0          4096                                   192.168.25.101:3001               0.0.0.0:*        users:(("docker-proxy",pid=4859,fd=8))
tcp      LISTEN     0          4096                                       127.0.0.54:53                 0.0.0.0:*users:(("systemd-resolve",pid=770,fd=17))
tcp      LISTEN     0          4096                                        127.0.0.1:10256              0.0.0.0:*        users:(("kubelite",pid=4123673,fd=93))
tcp      LISTEN     0          4096                                        127.0.0.1:10248              0.0.0.0:*users:(("kubelite",pid=4123673,fd=100))
tcp      LISTEN     0          4096                                        127.0.0.1:10249              0.0.0.0:*        users:(("kubelite",pid=4123673,fd=95))
tcp      LISTEN     0          4096                                   192.168.25.101:5432               0.0.0.0:*users:(("docker-proxy",pid=5206,fd=8))
tcp      LISTEN     0          4096                                    127.0.0.53%lo:53                 0.0.0.0:*        users:(("systemd-resolve",pid=770,fd=15))
tcp      LISTEN     0          4096                                   192.168.25.101:3306               0.0.0.0:*users:(("docker-proxy",pid=4659,fd=8))
tcp      LISTEN     0          4096                                        127.0.0.1:19001              0.0.0.0:*        users:(("k8s-dqlite",pid=1172,fd=17))
tcp      LISTEN     0          4096                                          0.0.0.0:8080               0.0.0.0:*users:(("docker-proxy",pid=32500,fd=8))
tcp      LISTEN     0          4096                                          0.0.0.0:1883               0.0.0.0:*        users:(("docker-proxy",pid=5113,fd=8))
tcp      LISTEN     0          4096                                   192.168.25.101:8000               0.0.0.0:*users:(("docker-proxy",pid=3524247,fd=8))
tcp      LISTEN     0          4096                                          0.0.0.0:8001               0.0.0.0:*        users:(("docker-proxy",pid=3513291,fd=8))
tcp      LISTEN     0          4096                                        127.0.0.1:9099               0.0.0.0:*users:(("calico-node",pid=4127381,fd=7))
tcp      LISTEN     0          4096*:25000                    *:*        users:(("cluster-agent",pid=4121667,fd=3))
tcp      LISTEN     0          4096                                                *:2377                     *:*        users:(("dockerd",pid=1510,fd=139))
tcp      LISTEN     0          4096                                             [::]:22                    [::]:*        users:(("sshd",pid=240904,fd=4),("systemd",pid=1,fd=212))
tcp      LISTEN     0          4096                                                *:10259                    *:*        users:(("kubelite",pid=4123673,fd=102))
tcp      LISTEN     0          4096*:10257                    *:*        users:(("kubelite",pid=4123673,fd=104))
tcp      LISTEN     0          4096                                                *:10250                    *:*        users:(("kubelite",pid=4123673,fd=99))
tcp      LISTEN     0          4096*:16443                    *:*        users:(("kubelite",pid=4123673,fd=4))
tcp      LISTEN     0          4096                                                *:9090                     *:*        users:(("cockpit-tls",pid=5321,fd=3),("systemd",pid=1,fd=188))
tcp      LISTEN     0          4096                                             [::]:3005                  [::]:*        users:(("docker-proxy",pid=3514034,fd=8))
tcp      LISTEN     0          4096                                                *:9001                     *:*        users:(("prometheus",pid=1737,fd=8))
tcp      LISTEN     0          4096           [fd7a:115c:a1e0::bc4e:3f5b]%tailscale0:56216                 [::]:*        users:(("tailscaled",pid=1188,fd=23))
tcp      LISTEN     0          4096                                                *:5201                     *:*        users:(("iperf3",pid=1146,fd=3))
tcp      LISTEN     0          4096                                             [::]:8080                  [::]:*        users:(("docker-proxy",pid=32507,fd=8))
tcp      LISTEN     0          511                                                 *:8081                     *:*        users:(("httpd",pid=15082,fd=4),("httpd",pid=9840,fd=4),("httpd",pid=9839,fd=4),("httpd",pid=9838,fd=4),("httpd",pid=9730,fd=4))
tcp      LISTEN     0          4096                                                *:7946                     *:*        users:(("dockerd",pid=1510,fd=116))
tcp      LISTEN     0          4096                                             [::]:1883                  [::]:*        users:(("docker-proxy",pid=5127,fd=8))
tcp      LISTEN     0          4096                                             [::]:8001                  [::]:*        users:(("docker-proxy",pid=3513298,fd=8))

===== 2. PORT TCP LISTENING =====
State       Recv-Q      Send-Q                                    Local Address:Port             Peer Address:Port      Process
LISTEN      0           4096                                          127.0.0.1:37941                 0.0.0.0:*users:(("containerd",pid=4123118,fd=13))
LISTEN      0           4096                                      100.106.63.90:3306                  0.0.0.0:*          users:(("docker-proxy",pid=4652,fd=8))
LISTEN      0           4096                                          127.0.0.1:1338                  0.0.0.0:*users:(("containerd",pid=4123118,fd=3))
LISTEN      0           4096                                      100.106.63.90:5432                  0.0.0.0:*          users:(("docker-proxy",pid=5200,fd=8))
LISTEN      0           4096                           100.106.63.90%tailscale0:34098                 0.0.0.0:*users:(("tailscaled",pid=1188,fd=22))
LISTEN      0           4096                                            0.0.0.0:22                    0.0.0.0:*          users:(("sshd",pid=240904,fd=3),("systemd",pid=1,fd=211))
LISTEN      0           4096                                     192.168.25.101:5001                  0.0.0.0:*users:(("docker-proxy",pid=5253,fd=8))
LISTEN      0           4096                                            0.0.0.0:3005                  0.0.0.0:*          users:(("docker-proxy",pid=3514025,fd=8))
LISTEN      0           4096                                     192.168.25.101:3002                  0.0.0.0:*users:(("docker-proxy",pid=4516,fd=8))
LISTEN      0           4096                                     192.168.25.101:3001                  0.0.0.0:*          users:(("docker-proxy",pid=4859,fd=8))
LISTEN      0           4096                                         127.0.0.54:53                    0.0.0.0:*users:(("systemd-resolve",pid=770,fd=17))
LISTEN      0           4096                                          127.0.0.1:10256                 0.0.0.0:*          users:(("kubelite",pid=4123673,fd=93))
LISTEN      0           4096                                          127.0.0.1:10248                 0.0.0.0:*users:(("kubelite",pid=4123673,fd=100))
LISTEN      0           4096                                          127.0.0.1:10249                 0.0.0.0:*          users:(("kubelite",pid=4123673,fd=95))
LISTEN      0           4096                                     192.168.25.101:5432                  0.0.0.0:*users:(("docker-proxy",pid=5206,fd=8))
LISTEN      0           4096                                      127.0.0.53%lo:53                    0.0.0.0:*          users:(("systemd-resolve",pid=770,fd=15))
LISTEN      0           4096                                     192.168.25.101:3306                  0.0.0.0:*users:(("docker-proxy",pid=4659,fd=8))
LISTEN      0           4096                                          127.0.0.1:19001                 0.0.0.0:*          users:(("k8s-dqlite",pid=1172,fd=17))
LISTEN      0           4096                                            0.0.0.0:8080                  0.0.0.0:*users:(("docker-proxy",pid=32500,fd=8))
LISTEN      0           4096                                            0.0.0.0:1883                  0.0.0.0:*          users:(("docker-proxy",pid=5113,fd=8))
LISTEN      0           4096                                     192.168.25.101:8000                  0.0.0.0:*users:(("docker-proxy",pid=3524247,fd=8))
LISTEN      0           4096                                            0.0.0.0:8001                  0.0.0.0:*          users:(("docker-proxy",pid=3513291,fd=8))
LISTEN      0           4096                                          127.0.0.1:9099                  0.0.0.0:*users:(("calico-node",pid=4127381,fd=7))
LISTEN      0           4096*:25000                       *:*          users:(("cluster-agent",pid=4121667,fd=3))
LISTEN      0           4096                                                  *:2377                        *:*          users:(("dockerd",pid=1510,fd=139))
LISTEN      0           4096                                               [::]:22                       [::]:*          users:(("sshd",pid=240904,fd=4),("systemd",pid=1,fd=212))
LISTEN      0           4096                                                  *:10259                       *:*          users:(("kubelite",pid=4123673,fd=102))
LISTEN      0           4096*:10257                       *:*          users:(("kubelite",pid=4123673,fd=104))
LISTEN      0           4096                                                  *:10250                       *:*          users:(("kubelite",pid=4123673,fd=99))
LISTEN      0           4096*:16443                       *:*          users:(("kubelite",pid=4123673,fd=4))
LISTEN      0           4096                                                  *:9090                        *:*          users:(("cockpit-tls",pid=5321,fd=3),("systemd",pid=1,fd=188))
LISTEN      0           4096                                               [::]:3005                     [::]:*          users:(("docker-proxy",pid=3514034,fd=8))
LISTEN      0           4096                                                  *:9001                        *:*          users:(("prometheus",pid=1737,fd=8))
LISTEN      0           4096             [fd7a:115c:a1e0::bc4e:3f5b]%tailscale0:56216                    [::]:*          users:(("tailscaled",pid=1188,fd=23))
LISTEN      0           4096                                                  *:5201                        *:*          users:(("iperf3",pid=1146,fd=3))
LISTEN      0           4096                                               [::]:8080                     [::]:*          users:(("docker-proxy",pid=32507,fd=8))
LISTEN      0           511                                                   *:8081                        *:*          users:(("httpd",pid=15082,fd=4),("httpd",pid=9840,fd=4),("httpd",pid=9839,fd=4),("httpd",pid=9838,fd=4),("httpd",pid=9730,fd=4))
LISTEN      0           4096                                                  *:7946                        *:*          users:(("dockerd",pid=1510,fd=116))
LISTEN      0           4096                                               [::]:1883                     [::]:*          users:(("docker-proxy",pid=5127,fd=8))
LISTEN      0           4096                                               [::]:8001                     [::]:*          users:(("docker-proxy",pid=3513298,fd=8))

===== 3. PORT UDP LISTENING =====
State    Recv-Q   Send-Q     Local Address:Port        Peer Address:Port   Process
UNCONN   0        960              0.0.0.0:41641            0.0.0.0:*users:(("tailscaled",pid=1188,fd=19))
UNCONN   0        0                0.0.0.0:4789             0.0.0.0:*
UNCONN   0        0             127.0.0.54:53               0.0.0.0:*users:(("systemd-resolve",pid=770,fd=16))
UNCONN   0        0          127.0.0.53%lo:53               0.0.0.0:*       users:(("systemd-resolve",pid=770,fd=14))
UNCONN   0        0                   [::]:41641               [::]:*users:(("tailscaled",pid=1188,fd=18))
UNCONN   0        0*:7946                   *:*       users:(("dockerd",pid=1510,fd=118))
fa@fa:~$
