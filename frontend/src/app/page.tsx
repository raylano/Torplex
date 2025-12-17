'use client'

import { useEffect, useState } from 'react'
import {
    Film,
    Tv,
    Clock,
    CheckCircle,
    AlertCircle,
    HardDrive,
    Activity,
    TrendingUp
} from 'lucide-react'
import { api, Stats, MediaItem } from '@/lib/api'
import MediaCard from '@/components/MediaCard'

export default function Dashboard() {
    const [stats, setStats] = useState<Stats | null>(null)
    const [recentItems, setRecentItems] = useState<MediaItem[]>([])
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        async function fetchData() {
            try {
                const [statsData, libraryData] = await Promise.all([
                    api.getStats(),
                    api.getLibrary({ page: 1, pageSize: 8 })
                ])
                setStats(statsData)
                setRecentItems(libraryData.items)
            } catch (error) {
                console.error('Failed to fetch dashboard data:', error)
            } finally {
                setLoading(false)
            }
        }
        fetchData()
    }, [])

    if (loading) {
        return (
            <div className="flex items-center justify-center h-full">
                <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-primary-500"></div>
            </div>
        )
    }

    const statCards = [
        {
            label: 'Total Items',
            value: stats?.total || 0,
            icon: Film,
            color: 'text-primary-400',
            bgColor: 'bg-primary-500/10'
        },
        {
            label: 'Completed',
            value: stats?.counts.completed || 0,
            icon: CheckCircle,
            color: 'text-green-400',
            bgColor: 'bg-green-500/10'
        },
        {
            label: 'In Progress',
            value: (stats?.counts.requested || 0) + (stats?.counts.indexed || 0) +
                (stats?.counts.scraped || 0) + (stats?.counts.downloading || 0) +
                (stats?.counts.downloaded || 0) + (stats?.counts.symlinked || 0),
            icon: Clock,
            color: 'text-yellow-400',
            bgColor: 'bg-yellow-500/10'
        },
        {
            label: 'Failed',
            value: stats?.counts.failed || 0,
            icon: AlertCircle,
            color: 'text-red-400',
            bgColor: 'bg-red-500/10'
        },
    ]

    return (
        <div className="space-y-8 animate-fade-in">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold gradient-text">Dashboard</h1>
                    <p className="text-gray-400 mt-1">Welcome to Torplex</p>
                </div>
                <div className="flex items-center gap-4">
                    <div className={`flex items-center gap-2 px-4 py-2 rounded-lg glass ${stats?.mount_status ? 'text-green-400' : 'text-red-400'
                        }`}>
                        <HardDrive size={18} />
                        <span className="text-sm font-medium">
                            {stats?.mount_status ? 'Mount Active' : 'Mount Inactive'}
                        </span>
                    </div>
                </div>
            </div>

            {/* Stats Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                {statCards.map((stat) => (
                    <div
                        key={stat.label}
                        className="glass rounded-2xl p-6 card-hover"
                    >
                        <div className="flex items-start justify-between">
                            <div>
                                <p className="text-gray-400 text-sm font-medium">{stat.label}</p>
                                <p className="text-3xl font-bold mt-2">{stat.value}</p>
                            </div>
                            <div className={`p-3 rounded-xl ${stat.bgColor}`}>
                                <stat.icon className={stat.color} size={24} />
                            </div>
                        </div>
                    </div>
                ))}
            </div>

            {/* Provider Status */}
            <div className="glass rounded-2xl p-6">
                <div className="flex items-center gap-3 mb-4">
                    <Activity className="text-primary-400" size={20} />
                    <h2 className="text-xl font-semibold">Provider Status</h2>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                    {stats?.providers && Object.entries(stats.providers).map(([name, configured]) => (
                        <div
                            key={name}
                            className={`flex items-center gap-3 p-4 rounded-xl ${configured ? 'bg-green-500/10' : 'bg-gray-500/10'
                                }`}
                        >
                            <div className={`w-2 h-2 rounded-full ${configured ? 'bg-green-400' : 'bg-gray-500'
                                }`} />
                            <span className="text-sm font-medium capitalize">
                                {name.replace('_', ' ')}
                            </span>
                        </div>
                    ))}
                </div>
            </div>

            {/* Recent Items */}
            <div>
                <div className="flex items-center gap-3 mb-6">
                    <TrendingUp className="text-primary-400" size={20} />
                    <h2 className="text-xl font-semibold">Recent Activity</h2>
                </div>

                {recentItems.length > 0 ? (
                    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-4 gap-4">
                        {recentItems.map((item) => (
                            <MediaCard key={item.id} item={item} />
                        ))}
                    </div>
                ) : (
                    <div className="glass rounded-2xl p-12 text-center">
                        <Film className="mx-auto text-gray-500 mb-4" size={48} />
                        <p className="text-gray-400">No items yet. Search for something to add!</p>
                    </div>
                )}
            </div>
        </div>
    )
}
