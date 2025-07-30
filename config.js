require('dotenv').config();

module.exports = {
  channelAccessToken: process.env.LINE_CHANNEL_ACCESS_TOKEN || 'n3dIAErhnUGmlsBXDy/N2SLqd9bj98BxU/Yl+hRa3Wa4i17+kZY5szmn6aj2DKH0InFwUljSFdl83VWeFNcv4DW90zry+7ZpeeNhnhMe2F1dWgA6dSDQl3XXIguGQbf1iUavmx+Si5SFxJh84r4ScgdB04t89/1O/w1cDnyilFU=',
  channelSecret: process.env.LINE_CHANNEL_SECRET || 'aa49542cb806c9bf0870cc61a2b21a4c',
  port: process.env.PORT || 5000
}; 