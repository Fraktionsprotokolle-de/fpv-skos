<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet 
    version="2.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:tei="http://www.tei-c.org/ns/1.0"
    exclude-result-prefixes="tei">

    <xsl:output method="xml" indent="yes" encoding="UTF-8"/>

    <!-- Root Template -->
    <xsl:template match="/">

        <body>
            <ul xml:space="default">

                <!-- Annahme: Konzepte sind <entry> oder <item> oder ähnliches mit @xml:id -->
                <!-- Falls bei dir anders, passe den Pfad hier an -->

                <xsl:for-each select="//tei:*[@xml:id]">

                    <xsl:variable name="entityType"
                        select="normalize-space(tei:note[@type='entityType'][1])"/>

                    <xsl:variable name="prefTerm"
                        select="normalize-space(tei:term[@type='pref'][1])"/>

                    <li>
                        <xsl:attribute name="type">
                            <xsl:value-of select="$entityType"/>
                        </xsl:attribute>

                        <xsl:attribute name="id">
                            <xsl:value-of select="@xml:id"/>
                        </xsl:attribute>

                        <xsl:attribute name="val">
                            <xsl:value-of select="$prefTerm"/>
                        </xsl:attribute>
                    </li>

                </xsl:for-each>

            </ul>
        </body>

    </xsl:template>

</xsl:stylesheet>