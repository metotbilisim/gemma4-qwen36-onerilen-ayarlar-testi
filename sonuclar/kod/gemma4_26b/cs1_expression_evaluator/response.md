```csharp
using System;
using System.Globalization;

namespace Bench
{
    public static class ExpressionEvaluator
    {
        private static string _expression;
        private static int _pos;

        /// <summary>
        /// Evaluates a mathematical expression string.
        /// </summary>
        /// <param name="expression">The expression to evaluate.</param>
        /// <returns>The result of the evaluation as a double.</returns>
        /// <exception cref="FormatException">Thrown when the input is empty, whitespace-only, or contains invalid syntax/numbers.</exception>
        /// <exception cref="DivideByZeroException">Thrown when a division by zero is attempted.</exception>
        public static double Evaluate(string expression)
        {
            if (string.IsNullOrWhiteSpace(expression))
            {
                throw new FormatException("Expression cannot be empty or whitespace.");
            }

            _expression = expression;
            _pos = 0;

            double result = ParseExpression();

            SkipWhitespace();

            if (_pos < _expression.Length)
            {
                throw new FormatException("Unexpected characters at end of expression.");
            }

            return result;
        }

        // Expression -> Term { ('+' | '-') Term }
        private static double ParseExpression()
        {
            double left = ParseTerm();

            while (true)
            {
                SkipWhitespace();
                if (_pos >= _expression.Length) break;

                char op = _expression[_pos];
                if (op == '+' || op == '-')
                {
                    _pos++;
                    double right = ParseTerm();
                    if (op == '+') left += right;
                    else left -= right;
                }
                else
                {
                    break;
                }
            }

            return left;
        }

        // Term -> Unary { ('*' | '/') Unary }
        private static double ParseTerm()
        {
            double left = ParseUnary();

            while (true)
            {
                SkipWhitespace();
                if (_pos >= _expression.Length) break;

                char op = _expression[_pos];
                if (op == '*' || op == '/')
                {
                    _pos++;
                    double right = ParseUnary();
                    if (op == '*')
                    {
                        left *= right;
                    }
                    else
                    {
                        if (right == 0) throw new DivideByZeroException();
                        left /= right;
                    }
                }
                else
                {
                    break;
                }
            }

            return left;
        }

        // Unary -> ('+' | '-') Unary | Power
        private static double ParseUnary()
        {
            SkipWhitespace();
            if (_pos >= _expression.Length) throw new FormatException("Unexpected end of expression.");

            char op = _expression[_pos];
            if (op == '+' || op == '-')
            {
                _pos++;
                double val = ParseUnary();
                return op == '-' ? -val : val;
            }

            return ParsePower();
        }

        // Power -> Factor [ '^' Unary ]
        private static double ParsePower()
        {
            double left = ParseFactor();

            SkipWhitespace();
            if (_pos < _expression.Length && _expression[_pos] == '^')
            {
                _pos++; // consume '^'
                // Calling ParseUnary allows for unary signs in the exponent (e.g., 2^-1)
                // and maintains right-associativity (e.g., 2^3^2 = 2^(3^2))
                double right = ParseUnary();
                return Math.Pow(left, right);
            }

            return left;
        }

        // Factor -> Number | '(' Expression ')'
        private static double ParseFactor()
        {
            SkipWhitespace();
            if (_pos >= _expression.Length) throw new FormatException("Unexpected end of expression.");

            char current = _expression[_pos];

            if (char.IsDigit(current) || current == '.')
            {
                return ParseNumber();
            }
            else if (current == '(')
            {
                _pos++; // consume '('
                double val = ParseExpression();
                SkipWhitespace();
                if (_pos >= _expression.Length || _expression[_pos] != ')')
                {
                    throw new FormatException("Mismatched parentheses.");
                }
                _pos++; // consume ')'
                return val;
            }
            else
            {
                throw new FormatException($"Unexpected character '{current}' where a number or '(' was expected.");
            }
        }

        private static double ParseNumber()
        {
            int start = _pos;
            bool hasDot = false;

            while (_pos < _expression.Length && (char.IsDigit(_expression[_pos]) || _expression[_pos] == '.'))
            {
                if (_expression[_pos] == '.')
                {
                    if (hasDot) throw new FormatException("Malformed number: multiple decimal points.");
                    hasDot = true;
                }
                _pos++;
            }

            string part = _expression.Substring(start, _pos - start);

            if (!double.TryParse(part, NumberStyles.Float, CultureInfo.InvariantCulture, out double result))
            {
                throw new FormatException($"Invalid number format: '{part}'.");
            }

            return result;
        }

        private static void SkipWhitespace()
        {
            while (_pos < _expression.Length && char.IsWhiteSpace(_expression[_pos]))
            {
                _pos++;
            }
        }
    }
}
```