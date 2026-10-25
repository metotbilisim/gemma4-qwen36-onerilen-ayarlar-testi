```php
<?php

final class RomanNumerals
{
    private const MAP = [
        'I' => 1,
        'V' => 5,
        'X' => 10,
        'L' => 50,
        'C' => 100,
        'D' => 500,
        'M' => 1000,
    ];

    private const TROMAN_VALUES = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1];
    private const TROMAN_SYMBOLS = ['M', 'CM', 'D', 'CD', 'C', 'XC', 'L', 'XL', 'X', 'IX', 'V', 'IV', 'I'];

    public static function toRoman(int $n): string
    {
        if ($n < 1 || $n > 3999) {
            throw new \InvalidArgumentException('Number must be between 1 and 3999');
        }

        $result = '';
        for ($i = 0; $i < count(self::TROMAN_VALUES); $i++) {
            while ($n >= self::TROMAN_VALUES[$i]) {
                $result .= self::TROMAN_SYMBOLS[$i];
                $n -= self::TROMAN_VALUES[$i];
            }
        }
        return $result;
    }

    public static function fromRoman(string $s): int
    {
        if ($s === '') {
            throw new \InvalidArgumentException('String cannot be empty');
        }

        if (strspn($s, 'IVXLCDM') !== strlen($s)) {
            throw new \InvalidArgumentException('Invalid characters in Roman numeral string');
        }

        $num = 0;
        $prev = 0;
        $len = strlen($s);
        
        for ($i = $len - 1; $i >= 0; $i--) {
            $val = self::MAP[$s[$i]];
            if ($val < $prev) {
                $num -= $val;
            } else {
                $num += $val;
            }
            $prev = $val;
        }

        if ($num < 1 || $num > 3999) {
            throw new \InvalidArgumentException('Parsed number out of range');
        }

        if (self::toRoman($num) !== $s) {
            throw new \InvalidArgumentException('Non-canonical Roman numeral form');
        }

        return $num;
    }

    public static function add(string $a, string $b): string
    {
        $numA = self::fromRoman($a);
        $numB = self::fromRoman($b);
        $sum = $numA + $numB;

        if ($sum < 1 || $sum > 3999) {
            throw new \InvalidArgumentException('Sum is out of range (1..3999)');
        }

        return self::toRoman($sum);
    }
}
```