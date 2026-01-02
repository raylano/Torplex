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
    TrendingUp,
    RefreshCw
} from 'lucide-react'
import { api, Stats, MediaItem } from '@/lib/api'
import MediaCard from '@/components/MediaCard'

export default function Dashboard() {
    const [stats, setStats] = useState<Stats | null>(null)
    const [recentItems, setRecentItems] = useState<MediaItem[]>([])
    const [loading, setLoading] = useState(true)
    const [showResetConfirm, setShowResetConfirm] = useState(false)
    const [resetting, setResetting] = useState(false)

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

    const handleResetAll = async () => {
        setResetting(true)
        try {
            const result = await api.retryAllMedia()
            alert(`✅ ${result.message}`)
            // Refresh the page data
            window.location.reload()
        } catch (error) {
            console.error('Reset failed:', error)
            alert('❌ Reset failed. Check console for details.')
        } finally {
            setResetting(false)
            setShowResetConfirm(false)
        }
    }

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
                    <button
                        onClick={() => setShowResetConfirm(true)}
                        className="flex items-center gap-2 px-4 py-2 rounded-lg glass text-orange-400 hover:bg-orange-500/20 transition-colors"
                        title="Reset all media items and re-process"
                    >
                        <RefreshCw size={18} />
                        <span className="text-sm font-medium">Reset All</span>
                    </button>
                    <div className={`flex items-center gap-2 px-4 py-2 rounded-lg glass ${stats?.mount_status ? 'text-green-400' : 'text-red-400'
                        }`}>
                        <HardDrive size={18} />
                        <span className="text-sm font-medium">
                            {stats?.mount_status ? 'Mount Active' : 'Mount Inactive'}
                        </span>
                    </div>
                </div>
            </div>

            {/* Reset Confirmation Modal */}
            {showResetConfirm && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="glass rounded-2xl p-6 max-w-md mx-4">
                        <h3 className="text-xl font-bold text-red-400 mb-4">⚠️ Reset All Media?</h3>
                        <p className="text-gray-300 mb-4">
                            This will:
                        </p>
                        <ul className="text-gray-400 text-sm mb-6 space-y-2">
                            <li>• Delete all existing symlinks</li>
                            <li>• Delete all episode records</li>
                            <li>• Re-fetch metadata from TMDB</li>
                            <li>• Re-process everything from scratch</li>
                        </ul>
                        <div className="flex gap-4">
                            <button
                                onClick={() => setShowResetConfirm(false)}
                                className="flex-1 px-4 py-2 rounded-lg bg-gray-600 hover:bg-gray-500 transition-colors"
                                disabled={resetting}
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleResetAll}
                                className="flex-1 px-4 py-2 rounded-lg bg-red-600 hover:bg-red-500 transition-colors flex items-center justify-center gap-2"
                                disabled={resetting}
                            >
                                {resetting ? (
                                    <RefreshCw className="animate-spin" size={18} />
                                ) : (
                                    <RefreshCw size={18} />
                                )}
                                {resetting ? 'Resetting...' : 'Reset All'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

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
