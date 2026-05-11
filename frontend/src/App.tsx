import { Route, Routes } from 'react-router';
import Feed from './components/feed/Feed';
import DrawingPage from './components/drawing-page/DrawingPage';
import Navigator from './components/Navigator';

function App() {
    return (
        <Routes>
            <Route path="/feed" element={<Feed />} />
            <Route path="/feed/:id" element={<DrawingPage />} />
            <Route path="*" element={<Navigator />} />
        </Routes>
    );
}

export default App;
