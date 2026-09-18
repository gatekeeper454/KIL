"""Closed Bash-only Envoy control producers; no in-image helper dependency.

The refusal grammar is a reviewed textual classification, not numeric errno
exposure or a claim that the pinned image's diagnostic has been observed.
Unknown grammar fails closed. The controller's outer timeout also remains
necessary: Bash read deadlines do not prove termination of a remote connect.
JSON schema and the four exact zero gauges are validated by the proof registry.
"""

_COMMON = r'''
export LC_ALL=C LANG=C
unset BASH_ENV ENV CDPATH GLOBIGNORE

fail() { printf 'envoy_control:%s\n' "$1" >&2; exit 20; }
remaining() {
    remaining_seconds=$((deadline - SECONDS))
    ((remaining_seconds > 0)) || fail timeout
}

probe_child() {
    /bin/bash -pc 'exec 4<>/dev/tcp/127.0.0.1/8080' kil-v3b2-probe
}
admin_open() { exec 3<>/dev/tcp/127.0.0.1/9901; }

reject_probe_stdout() {
    local byte=''
    # A delimiter NUL or any other byte is nonempty stdout. Do not copy it.
    if IFS= read -r -d '' -n 1 byte; then
        printf '\036unexpected_stdout\036'
    elif [[ -n "$byte" ]]; then
        printf '\036unexpected_stdout\036'
    fi
}

require_refusal() {
    local wire='' read_status=0
    remaining
    # Both streams stay distinct until stdout has been classified. Its marker
    # can never equal part of the accepted stderr/exit grammar, regardless of
    # scheduling. Read up to one overflow byte and reject NUL and timeout.
    IFS= read -r -d '' -n 1025 -t "$remaining_seconds" wire < <(
        if probe_child 2>&1 > >(reject_probe_stdout); then
            probe_status=0
        else
            probe_status=$?
        fi
        printf '\036exit:%d\036' "$probe_status"
    ) || read_status=$?
    if [[ "$read_status" != 1 || ${#wire} -gt 1024 ]]; then
        printf '%s' "$wire" >&2
        fail probe_incomplete
    fi
    local expected=$'kil-v3b2-probe: connect: Connection refused\nkil-v3b2-probe: line 1: /dev/tcp/127.0.0.1/8080: Connection refused\n\036exit:1\036'
    if [[ "$wire" != "$expected" ]]; then
        # Bounded original stderr text is retained for diagnostic inspection;
        # the internal framing also distinguishes unexpected stdout/exit.
        printf '%s' "$wire" >&2
        fail refusal_unproved
    fi
}

read_http_line() {
    line=''
    local byte='' count=0
    while :; do
        remaining
        byte=''
        IFS= read -r -d '' -n 1 -t "$remaining_seconds" byte <&3 || fail http_line_incomplete
        [[ -n "$byte" ]] || fail http_nul
        ((count += 1))
        ((count <= 8192)) || fail http_line_oversized
        if [[ "$byte" == $'\n' ]]; then
            [[ "$line" == *$'\r' ]] || fail http_line_framing
            line=${line%$'\r'}
            return
        fi
        line+=$byte
    done
}


read_chunked_body() {
    local chunk_size=0 chunks=0 chunk='' framing='' extra='' read_status=0
    body=''
    while :; do
        read_http_line
        [[ "$line" =~ ^[0-9a-fA-F]{1,6}$ ]] || fail http_chunk_size
        chunk_size=$((16#$line))
        ((chunks += 1))
        ((chunks <= 4096 && chunk_size <= 1048576 && ${#body} + chunk_size <= 1048576)) || fail http_body_oversized
        if ((chunk_size == 0)); then
            read_http_line
            [[ -z "$line" ]] || fail http_chunk_trailers
            break
        fi
        remaining
        chunk=''
        IFS= read -r -d '' -n "$chunk_size" -t "$remaining_seconds" chunk <&3 || fail http_chunk_incomplete
        ((${#chunk} == chunk_size)) || fail http_chunk_incomplete
        remaining
        framing=''
        IFS= read -r -d '' -n 2 -t "$remaining_seconds" framing <&3 || fail http_chunk_framing
        [[ "$framing" == $'\r\n' ]] || fail http_chunk_framing
        body+=$chunk
    done
    remaining
    IFS= read -r -d '' -n 1 -t "$remaining_seconds" extra <&3 || read_status=$?
    [[ "$read_status" == 1 && -z "$extra" ]] || fail http_chunk_extra
    exec 3>&-
}

admin_response() {
    local request=$1 content_length='' transfer_encoding='' header_count=0 header_bytes=0 value=''
    admin_open || fail admin_connect
    # HTTP/1.1 is supported by the pinned admin listener. Explicit close
    # bounds EOF; only one unambiguous bounded chunked or length body is admitted.
    printf '%s' "$request" >&3 || fail admin_write
    read_http_line
    if [[ "$line" != 'HTTP/1.0 200 OK' && "$line" != 'HTTP/1.1 200 OK' ]]; then
        printf '%s\n' "$line" >&2
        fail admin_status
    fi
    while :; do
        read_http_line
        [[ -n "$line" ]] || break
        ((header_count += 1))
        ((header_bytes += ${#line} + 2))
        ((header_count <= 64 && header_bytes <= 16384)) || fail http_headers_oversized
        [[ "$line" =~ ^[A-Za-z0-9-]+:\ .* ]] || fail http_header_framing
        [[ "$line" != *[!\ -~]* ]] || fail http_header_control
        case "$line" in
            [Cc][Oo][Nn][Tt][Ee][Nn][Tt]-[Ll][Ee][Nn][Gg][Tt][Hh]:\ *)
                [[ -z "$content_length" ]] || fail http_duplicate_length
                value=${line#*: }
                [[ "$value" =~ ^(0|[1-9][0-9]{0,6})$ ]] || fail http_length_invalid
                content_length=$((10#$value))
                ((content_length <= 1048576)) || fail http_body_oversized
                ;;
            [Tt][Rr][Aa][Nn][Ss][Ff][Ee][Rr]-[Ee][Nn][Cc][Oo][Dd][Ii][Nn][Gg]:*)
                [[ -z "$transfer_encoding" && "${line#*: }" == 'chunked' ]] || fail http_transfer_coding
                transfer_encoding=chunked ;;
        esac
    done
    if [[ -n "$transfer_encoding" ]]; then
        [[ -z "$content_length" ]] || fail http_ambiguous_length
        read_chunked_body
        return
    fi
    remaining
    body=''
    local read_status=0 limit=1048576
    [[ -z "$content_length" ]] || limit=$content_length
    IFS= read -r -d '' -n "$((limit + 1))" -t "$remaining_seconds" body <&3 || read_status=$?
    exec 3>&-
    [[ "$read_status" == 1 && ${#body} -le "$limit" ]] || fail http_body_incomplete
    [[ -z "$content_length" || ${#body} == "$content_length" ]] || fail http_body_length
}
'''

ENVOY_DRAIN_SCRIPT = _COMMON + r'''
main() {
    deadline=$((SECONDS + 10))
    admin_response $'POST /drain_listeners HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'
    printf '{"drain_requested":true}\n'
}
main
'''

ENVOY_STATS_SCRIPT = _COMMON + r'''
main() {
    deadline=$((SECONDS + 10))
    require_refusal
    admin_response $'GET /stats?format=json HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n'
    # Preserve the response's members verbatim. This is framing, not a JSON
    # parser: duplicate keys, malformed JSON and gauge semantics fail at the
    # shared proof boundary, which cannot emit a terminal for those bytes.
    local prefix=${body%%\{*} root='' tail=''
    [[ "$prefix" != *[!$' \t\r\n']* ]] || fail stats_root
    root=${body#"$prefix"}
    tail=$root
    while [[ "$tail" == *[$' \t\r\n'] ]]; do tail=${tail%?}; done
    [[ "$root" == \{* && "$tail" == *\} ]] || fail stats_root
    printf '{"listener_refused":true,%s\n' "${root#\{}"
}
main
'''
