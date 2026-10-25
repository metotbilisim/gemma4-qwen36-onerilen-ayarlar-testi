```php
<?php

final class RomanNumerals
{
    /**
     * Converts an integer between 1 and 3999 to a Roman numeral.
     *
     * @param int $n
     * @return string
     * @throws \InvalidArgumentException
     */
    public static function toRoman(int $n): string
    {
        if ($n < 1 || $n > 3999) {
            throw new \InvalidArgumentException("Number must be between 1 and 3999.");
        }

        $map = [
            'M' => 1000,
            'CM' => 900,
            'D' => 500,
            'CD' => 400,
            'C' => 100,
            'XC' => 90,
            'L' => 50,
            'XL' => 40,
            'X' => 10,
            'IX' => 9,
            'V' => 5,
            'IV' => 4,
            'I' => 1,
        ];

        $result = '';
        foreach ($map as $roman => $value) {
            $count = intdiv($n, $value);
            $result .= str_repeat($roman, $count);
            $n %= $value;
        }

        return $result;
    }

    /**
     * Converts a canonical Roman numeral string back to an integer.
     *
     * @param string $s
     * @return int
     * @throws \InvalidArgumentException
     */
    public static function fromRoman(string $s): int
    {
        // Validate characters, case, and emptiness
        if ($s === '' || !preg_match('/^[IVXLCDM]+$/', $s)) {
            throw new \InvalidArgumentException("Invalid Roman numeral string.");
        }

        $map = [
            'I' => 1,
            'V' => 5,
            'X' => 10,
            'L' => 50,
            'C' => 100,
            'D' => 500,
            'M' => 1000,
        ];

        $total = 0;
        $prevValue = 0;
        $chars = str_split($s);
        
        // Parse backwards to handle subtractive forms easily
        for ($i = count($chars) - 1; $i >= 0; $i--) {
            $currentValue = $map[$chars[$i]];
            if ($currentValue < $prevValue) {
                $total -= $currentValue;
            } else {
                $total += $currentValue;
            }
            $prevValue = $currentValue;
        }

        /**
         * To ensure the numeral is strictly canonical (exactly as toRoman would produce),
         * we perform a round-trip check. This naturally rejects:
         * - Non-canonical forms like "IIII", "VV", "IC", "IIV", "XM", etc.
         * - Values outside the valid 1..3999 range (as toRoman will throw the exception).
         */
        if (self::toRoman($total) !== $s) {
            throw new \InvalidArgumentException("Non-canonical Roman numeral.");
        }

        return $total;
    }

    /**
     * Adds two Roman numerals and returns the result as a Roman numeral.
     *
     * @param string $a
     * @param string $b
     * @return string
     * @throws \InvalidArgumentException
     */
    public static function add(string $a, string $b): string
    {
        $valA = self::fromRoman($a);
        $valB = self::fromRoman($b);
        
        $sum = $valA + $valB;
        
        // toRoman will throw \InvalidArgumentException if $sum is out of 1..3999 range.
        return self::toRoman($sum);
    }
}
```