import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import { ApiError } from './lib/api-client';
import { PERMISSIONS_QUERY_KEY } from './hooks/usePermissions';
import './globals.css';

// A 403 means our cached permissions are out of date, so fetch them again.
function refreshPermissionsOnForbidden(error: Error) {
  if (error instanceof ApiError && error.status === 403) {
    queryClient.invalidateQueries({ queryKey: PERMISSIONS_QUERY_KEY });
  }
}

const queryClient = new QueryClient({
  queryCache: new QueryCache({ onError: refreshPermissionsOnForbidden }),
  mutationCache: new MutationCache({ onError: refreshPermissionsOnForbidden }),
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
