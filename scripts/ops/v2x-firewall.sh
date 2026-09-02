#!/usr/bin/env bash
# Block internet access to the CARLA RPC/stream ports (2000-2002, Docker-published,
# enforced in DOCKER-USER) and the host drive/twin ports (8765, 8190, 8865,
# enforced in INPUT). Loopback and established connections are unaffected;
# SSH (22) and nginx (443) stay open.
set -u

EXT4=$(ip route get 1.1.1.1 2>/dev/null | grep -oP 'dev \K\S+' || true)
if [ -n "$EXT4" ]; then
    iptables -C DOCKER-USER -i "$EXT4" -p tcp --dport 2000:2002 -m conntrack --ctstate NEW -j DROP 2>/dev/null || \
        iptables -I DOCKER-USER -i "$EXT4" -p tcp --dport 2000:2002 -m conntrack --ctstate NEW -j DROP
    iptables -C INPUT -i "$EXT4" -p tcp --dport 8765 -m conntrack --ctstate NEW -j DROP 2>/dev/null || \
        iptables -I INPUT -i "$EXT4" -p tcp --dport 8765 -m conntrack --ctstate NEW -j DROP
    iptables -C INPUT -i "$EXT4" -p tcp -m multiport --dports 8190,8865 -m conntrack --ctstate NEW -j DROP 2>/dev/null || \
        iptables -I INPUT -i "$EXT4" -p tcp -m multiport --dports 8190,8865 -m conntrack --ctstate NEW -j DROP
    echo "v2x-firewall: IPv4 rules active on $EXT4"
fi

EXT6=$(ip -6 route get 2606:4700:4700::1111 2>/dev/null | grep -oP 'dev \K\S+' || true)
if [ -n "$EXT6" ]; then
    if ip6tables -nL DOCKER-USER >/dev/null 2>&1; then
        ip6tables -C DOCKER-USER -i "$EXT6" -p tcp --dport 2000:2002 -m conntrack --ctstate NEW -j DROP 2>/dev/null || \
            ip6tables -I DOCKER-USER -i "$EXT6" -p tcp --dport 2000:2002 -m conntrack --ctstate NEW -j DROP
    fi
    ip6tables -C INPUT -i "$EXT6" -p tcp --dport 8765 -m conntrack --ctstate NEW -j DROP 2>/dev/null || \
        ip6tables -I INPUT -i "$EXT6" -p tcp --dport 8765 -m conntrack --ctstate NEW -j DROP
    ip6tables -C INPUT -i "$EXT6" -p tcp -m multiport --dports 8190,8865 -m conntrack --ctstate NEW -j DROP 2>/dev/null || \
        ip6tables -I INPUT -i "$EXT6" -p tcp -m multiport --dports 8190,8865 -m conntrack --ctstate NEW -j DROP
    echo "v2x-firewall: IPv6 rules active on $EXT6"
fi
