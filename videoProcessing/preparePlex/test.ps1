mkvmerge -o "E:/test2.mkv" `
--video-tracks 0 `
--audio-tracks 1,2 --language 1:ita --track-name 1:Italian --language 2:eng --track-name 2:ItalianSub `
--subtitle-tracks 3,6 --language 3:ita --track-name 3:Italian --language 6:eng --track-name 6:EngSub `
"E:/test.mkv"