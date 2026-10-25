```javascript
/**
 * Runs at most `limit` tasks at a time from an array of functions.
 * 
 * @param {Array<() => any>} taskFns - Array of zero-argument functions.
 * @param {number} limit - Maximum number of concurrent tasks.
 * @returns {Promise<Array<any>>} - Resolves with the array of results in original order.
 */
async function promisePool(taskFns, limit) {
  if (!Number.isInteger(limit) || limit <= 0) {
    throw new TypeError('limit must be a positive integer');
  }

  const n = taskFns.length;
  if (n === 0) return [];

  const results = new Array(n);
  let currentIndex = 0;
  let completedCount = 0;
  let hasError = false;

  return new Promise((resolve, reject) => {
    /**
     * A worker function that continuously picks the next available task
     * from the taskFns array until all tasks are finished or an error occurs.
     */
    const worker = async () => {
      while (currentIndex < n && !hasError) {
        const i = currentIndex++;

        // Double-check hasError in case another worker set it 
        // between the loop condition check and the increment.
        if (hasError) return;

        try {
          // taskFns[i]() may return a promise, a value, or throw synchronously.
          // await handles all three cases.
          const val = await taskFns[i]();

          // If an error occurred in another worker while this task was running, stop.
          if (hasError) return;

          results[i] = val;
          completedCount++;

          if (completedCount === n) {
            resolve(results);
          }
        } catch (err) {
          if (!hasError) {
            hasError = true;
            reject(err);
          }
          return;
        }
      }
    };

    // Start initial workers up to the specified limit.
    const actualLimit = Math.min(limit, n);
    for (let i = 0; i < actualLimit; i++) {
      worker();
    }
  });
}

/**
 * Retries a function with exponential backoff.
 * 
 * @param {Function} fn - Function to retry, receives the attempt number as an argument.
 * @param {Object} [options] - Configuration for retries.
 * @param {number} [options.retries=3] - Number of times to retry after the initial failure.
 * @param {number} [options.delayMs=0] - Initial delay in milliseconds.
 * @param {number} [options.factor=2] - Exponential backoff multiplier.
 * @param {Function} [options.shouldRetry=(err) => true] - Predicate to decide if we should retry.
 * @returns {Promise<any>} - Resolves with the function's result.
 */
async function retry(fn, options = {}) {
  const {
    retries = 3,
    delayMs = 0,
    factor = 2,
    shouldRetry = (err) => true
  } = options;

  let lastError;

  // Total attempts = 1 (initial call) + retries.
  for (let attempt = 1; attempt <= retries + 1; attempt++) {
    try {
      return await fn(attempt);
    } catch (err) {
      lastError = err;

      // If we still have retries left and the error allows it, wait and retry.
      if (attempt <= retries && shouldRetry(err)) {
        const delay = delayMs * Math.pow(factor, attempt - 1);
        if (delay > 0) {
          await new Promise((resolve) => setTimeout(resolve, delay));
        }
      } else {
        // Otherwise, give up and throw the last error encountered.
        throw lastError;
      }
    }
  }
}

module.exports = { promisePool, retry };
```