package com.nothingalternative.app

/**
 * Parses raw DNS query packets (UDP payload) to extract the queried domain name.
 * Only handles DNS queries (QR bit = 0). Responses and other types are ignored.
 */
object DnsPacketParser {

    /**
     * Returns the domain name from a DNS query payload, or null if
     * the packet is not a valid DNS query.
     */
    fun extractDomain(payload: ByteArray): String? {
        // Minimum DNS header is 12 bytes
        if (payload.size < 12) return null

        // Flags are bytes 2-3. QR bit is the highest bit of byte 2.
        // QR = 0 means query, QR = 1 means response — we only care about queries.
        val flags = ((payload[2].toInt() and 0xFF) shl 8) or (payload[3].toInt() and 0xFF)
        val isQuery = (flags and 0x8000) == 0
        if (!isQuery) return null

        // Question count is bytes 4-5
        val questionCount = ((payload[4].toInt() and 0xFF) shl 8) or (payload[5].toInt() and 0xFF)
        if (questionCount == 0) return null

        // Domain name starts at byte 12
        return parseDomainName(payload, 12)
    }

    /**
     * Reads a DNS-encoded domain name starting at [offset].
     * DNS encodes names as length-prefixed labels: 3www6google3com0
     */
    private fun parseDomainName(payload: ByteArray, offset: Int): String? {
        val labels = mutableListOf<String>()
        var i = offset

        while (i < payload.size) {
            val labelLen = payload[i].toInt() and 0xFF
            if (labelLen == 0) break  // root label — end of name

            // Pointer (compression) — not common in queries but handle gracefully
            if ((labelLen and 0xC0) == 0xC0) return null

            i++
            if (i + labelLen > payload.size) return null

            val label = String(payload, i, labelLen, Charsets.US_ASCII)
            labels.add(label)
            i += labelLen
        }

        if (labels.isEmpty()) return null
        return labels.joinToString(".")
    }
}
