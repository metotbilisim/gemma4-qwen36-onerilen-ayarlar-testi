```csharp
using System;
using System.Globalization;

namespace Bench
{
    public static class ExpressionEvaluator
    {
        public static double Evaluate(string expression)
        {
            if (string.IsNullOrWhiteSpace(expression))
                throw new FormatException("Expression cannot be empty or whitespace.");

            var parser = new Parser(expression);
            double result = parser.ParseExpression();
            parser.SkipWhitespace();
            if (parser._pos < parser._expr.Length)
                throw new FormatException("Unexpected characters at the end of the expression.");
            return result;
        }

        private sealed class Parser
        {
            private readonly string _expr;
            private int _pos;

            public Parser(string expr) { _expr = expr; _pos = 0; }

            public double ParseExpression()
            {
                double left = ParseTerm();
                while (Peek() is '+' or '-')
                {
                    char op = Consume();
                    double right = ParseTerm();
                    left = op == '+' ? left + right : left - right;
                }
                return left;
            }

            public double ParseTerm()
            {
                double left = ParseUnary();
                while (Peek() is '*' or '/')
                {
                    char op = Consume();
                    double right = ParseUnary();
                    if (op == '*')
                        left *= right;
                    else
                    {
                        if (right == 0) throw new DivideByZeroException();
                        left /= right;
                    }
                }
                return left;
            }

            public double ParseUnary()
            {
                if (Peek() is '+' or '-')
                {
                    char op = Consume();
                    double val = ParseUnary();
                    return op == '-' ? -val : val;
                }
                return ParsePower();
            }

            public double ParsePower()
            {
                double baseVal = ParseAtom();
                if (Peek() == '^')
                {
                    Consume();
                    double exp = ParsePower();
                    return Math.Pow(baseVal, exp);
                }
                return baseVal;
            }

            public double ParseAtom()
            {
                SkipWhitespace();
                if (Peek() == '(')
                {
                    Consume();
                    double val = ParseExpression();
                    SkipWhitespace();
                    if (Peek() != ')')
                        throw new FormatException("Mismatched parentheses.");
                    Consume();
                    return val;
                }
                return ParseNumber();
            }

            public double ParseNumber()
            {
                SkipWhitespace();
                int start = _pos;
                bool hasDot = false;
                bool hasDigit = false;

                while (_pos < _expr.Length)
                {
                    char c = _expr[_pos];
                    if (char.IsDigit(c))
                    {
                        hasDigit = true;
                        _pos++;
                    }
                    else if (c == '.' && !hasDot)
                    {
                        hasDot = true;
                        _pos++;
                    }
                    else
                    {
                        break;
                    }
                }

                if (!hasDigit)
                    throw new FormatException("Invalid number format.");

                string numStr = _expr.Substring(start, _pos - start);
                if (numStr.Contains(".."))
                    throw new FormatException("Invalid number format.");

                if (double.TryParse(numStr, NumberStyles.Float, CultureInfo.InvariantCulture, out double result))
                    return result;

                throw new FormatException("Invalid number format.");
            }

            private char Peek() => _pos < _expr.Length ? _expr[_pos] : '\0';
            private char Consume() => _expr[_pos++];
            private void SkipWhitespace()
            {
                while (_pos < _expr.Length && char.IsWhiteSpace(_expr[_pos])) _pos++;
            }
        }
    }
}
```