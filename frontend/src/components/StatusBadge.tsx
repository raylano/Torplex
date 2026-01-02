'use client'

import {
    Clock,
    Search,
    Download,
    CheckCircle,
    XCircle,
    Pause,
    Link,
    Database,
    Loader2
} from 'lucide-react'
import { clsx } from 'clsx'

interface StatusBadgeProps {
    status: string
    size?: 'sm' | 'md'
}

const statusConfig: Record<string, {
    label: string
    icon: any
    className: string
}> = {
    requested: {
        label: 'Requested',
        icon: Clock,
        className: 'status-requested',
    },
    indexed: {
        label: 'Indexed',
        icon: Database,
        className: 'status-indexed',
    },
    scraped: {
        label: 'Scraped',
        icon: Search,
        className: 'status-scraped',
    },
    downloading: {
        label: 'Downloading',
        icon: Loader2,
        className: 'status-downloading',
    },
    downloaded: {
        label: 'Downloaded',
        icon: Download,
        className: 'status-downloaded',
    },
    symlinked: {
        label: 'Symlinked',
        icon: Link,
        className: 'status-symlinked',
    },
    completed: {
        label: 'Completed',
        icon: CheckCircle,
        className: 'status-completed',
    },
    failed: {
        label: 'Failed',
        icon: XCircle,
        className: 'status-failed',
    },
    paused: {
        label: 'Paused',
        icon: Pause,
        className: 'status-paused',
    },
}

export default function StatusBadge({ status, size = 'sm' }: StatusBadgeProps) {
    const config = statusConfig[status] || statusConfig.requested
    const Icon = config.icon

    return (
        <div className={clsx(
            'inline-flex items-center gap-1 rounded-full border',
            config.className,
            size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-3 py-1 text-sm'
        )}>
            <Icon
                size={size === 'sm' ? 10 : 14}
                className={status === 'downloading' ? 'animate-spin' : ''}
            />
            <span className="font-medium">{config.label}</span>
        </div>
    )
}
