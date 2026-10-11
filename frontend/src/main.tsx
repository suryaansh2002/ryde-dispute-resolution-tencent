import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider, createBrowserRouter } from 'react-router-dom'
import './index.css'
import { Layout } from './components/Layout'
import { CaseDetail } from './routes/CaseDetail'
import { FileClaim } from './routes/FileClaim'
import { Home } from './routes/Home'
import { Insights } from './routes/Insights'
import { L2Console } from './routes/L2Console'
import { PartyPanel } from './routes/PartyPanel'
import { TracePage } from './routes/TracePage'

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: '/', element: <Home /> },
      { path: '/:role/:userId', element: <PartyPanel /> },
      { path: '/:role/:userId/file/:tripId', element: <FileClaim /> },
      { path: '/:role/:userId/case/:caseId', element: <CaseDetail /> },
      { path: '/trace', element: <TracePage /> },
      { path: '/trace/:caseId', element: <TracePage /> },
      { path: '/l2', element: <L2Console /> },
      { path: '/l2/:caseId', element: <L2Console /> },
      { path: '/insights', element: <Insights /> },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
