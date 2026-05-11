import { useEffect } from 'react';
import { useNavigate } from 'react-router';

const Navigator = () => {
    const navigate = useNavigate();
    useEffect(() => {
        navigate('/feed');
    }, []);
    return <div></div>;
};

export default Navigator;
