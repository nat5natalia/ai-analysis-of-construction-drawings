export const formatDate = (isoString: string): string => {
    const date = new Date(isoString);

    const day = date.getDate();
    const year = date.getFullYear();
    const hours = date.getHours().toString().padStart(2, '0');
    const minutes = date.getMinutes().toString().padStart(2, '0');

    const months = [
        'января',
        'февраля',
        'марта',
        'апреля',
        'мая',
        'июня',
        'июля',
        'августа',
        'сентября',
        'октября',
        'ноября',
        'декабря',
    ];

    const monthName = months[date.getMonth()];

    return `${day} ${monthName} ${year}, ${hours}:${minutes}`;
};
