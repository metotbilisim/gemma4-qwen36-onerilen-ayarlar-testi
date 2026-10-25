```javascript
'use strict';

async function promisePool(taskFns, limit) {
  if (!Number.isInteger(limit) || limit <= 0) {
    throw new TypeError('limit must be a positive integer');
  }
  if (taskFns.length === 0) return [];

  const results = new Array(taskFns.length);
  let currentIndex = 0;
  let activeTasks = 0;
  let hasRejection = false;

  const run = () => new Promise((resolve, reject) => {
    if (hasRejection) {
      resolve();
      return;
    }
    if (activeTasks === 0 && currentIndex >= taskFns.length) {
      resolve(results);
      return;
    }

    const startNext = () => {
      if (hasRejection) return;
      while (activeTasks < limit && currentIndex < taskFns.length && !hasRejection) {
        const idx = currentIndex++;
        activeTasks++;
        Promise.resolve()
          .then(() => taskFns[idx]())
          .then(res => {
            results[idx] = res;
          })
          .catch(err => {
            if (!hasRejection) {
              hasRejection = true;
              reject(err);
            }
          })
          .finally(() => {
            activeTasks--;
            startNext();
          });
      }
    };
    startNext();
  });

  return run();
}

async function retry(fn, options) {
  const { retries = 3, delayMs = 0, factor = 2, shouldRetry = (err) => true } = options || {};
  let lastError;

  for (let attempt = 1; attempt <= retries + 1; attempt++) {
    try {
      return await fn(attempt);
    } catch (err) {
      lastError = err;
      if (attempt <= retries && shouldRetry(err)) {
        const delay = delayMs * factor ** (attempt - 1);
        await new Promise(resolve => setTimeout(resolve, delay));
      } else {
        break;
      }
    }
  }

  throw lastError;
}

module.exports = { promisePool, retry };
```