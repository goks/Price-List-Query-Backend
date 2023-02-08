import QtQuick 2.15
import QtQuick.Window 2.15
import QtQuick.Controls 2.15


Window {
    id: window
    width: 753
    height: 589
    visible: true
    title: "Staff App Price Updater"

    FontLoader { id: boldPoppins; name: "Poppins"; source: "../fonts/Poppins-Bold.ttf" }
    FontLoader { id: regularPoppins; name: "Poppins"; source: "../fonts/Poppins-Regular.ttf" }
    FontLoader { id: semiboldPoppins; name: "Poppins SemiBold"; source: "../fonts/Poppins-SemiBold.ttf" }
    FontLoader { id: mediumPoppins; name: "Poppins Medium"; source: "../fonts/Poppins-Medium.ttf" }
    //    LinearGradient {
    //            anchors.fill: parent
    //            start: Qt.point(0, 0)
    //            end: Qt.point(0, 300)
    //            gradient: Gradient {
    //                GradientStop { position: 0.0; color: "white" }
    //                GradientStop { position: 1.0; color: "black" }
    //            }
    //        }

    Rectangle
    {
        id: loadingMaskRectangle
        visible: backend.mainScreenLoadingStatus
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.bottomMargin: -1
        color: "#e2e2e2e2"
        z:1

        BusyIndicator {
            id: mainBusyIndicator
            anchors.verticalCenter: parent.verticalCenter
            anchors.horizontalCenter: parent.horizontalCenter
            running: backend.mainScreenLoadingStatus
        }


    }

    Rectangle
    {
        id: rectangle1
        visible: true
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.bottomMargin: -1
        gradient: Gradient
        {
            GradientStop {position: 0.000;color: "#9C27B0"}
            GradientStop {position: 0.5;color: "#F44336"}
            GradientStop {position: 1.000;color:"#2196F3"}
        }


        Rectangle {
            id: headerBox
            height: 62
            color: Qt.rgba(1,1,1,0)
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.topMargin: 0
            anchors.rightMargin: 0
            anchors.leftMargin: 0
        }
        Text {
            id: heading
            color: "#d1b5d1"
            text: qsTr("Gokul Agencies Staff App Price Updater")
            anchors.left: headerBox.right
            anchors.right: headerBox.left
            anchors.top: headerBox.bottom
            anchors.bottom: headerBox.top
            font.pixelSize: 24
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            minimumPointSize: 24
            minimumPixelSize: 24
            font.family: semiboldPoppins.name
            anchors.rightMargin: 0
            anchors.leftMargin: 0
            anchors.bottomMargin: 0
            anchors.topMargin: 0
        }

        Rectangle {
            id: border1
            height: 1
            color: Qt.rgba(226,226,226,.26)
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: headerBox.bottom
            anchors.topMargin: 0
            anchors.rightMargin: 0
            anchors.leftMargin: 0
        }

        Text {
            id: lastUpdatedOnText
            color: "#e2e2e2"
            //            text: qsTr("Last uploaded on 01-02-2023 15:52.")
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: headerBox.bottom
            font.pixelSize: 25
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            font.family: regularPoppins.name
            anchors.topMargin: 64
            anchors.rightMargin: 0
            anchors.leftMargin: 0
            text: backend.lastUpdatedTime
        }

        Button {
            id: updatePriceListButton
            width: 299
            height: 76
            text: "<font color='#ffffff'>" + "Update Pricelist" + "</font>"
            //            qsTr("Update Pricelist")
            anchors.top: lastUpdatedOnText.bottom
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.horizontalCenterOffset: 0
            font.pointSize: 20
            font.family: mediumPoppins.name
            anchors.topMargin: 53
            autoRepeat: false
            onPressed : backend.beginUploading()

            contentItem: Text {
                id: text1
                text: updatePriceListButton.text
                font: updatePriceListButton.font
                opacity: enabled ? 1.0 : 0.3
                color: updatePriceListButton.down ? "#17a81a" : "#ffffff"
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight


            }
            background: Rectangle {
                radius: 10
                color: parent.down ? "#bbbbbb" :
                                     (parent.hovered ? "#d6d6d6" : Qt.rgba(0,0,256,0))
                border.color: "#ffffff"
            }


        }
        BusyIndicator {
            id: busyIndicator
            x: 112
            y: 16
            width: 82
            height: 64
            visible: true
            running: backend.itemUpdationStatus
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: -34
            anchors.horizontalCenterOffset: -7
            anchors.horizontalCenter: parent.horizontalCenter
        }
        Text { 
            id: connectionSuccessText
            color: "#d1b5d1"
//             text: qsTr("Busy Connection Succeeded")
            text: backend.connectionSuccessText
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: updatePriceListButton.bottom
            font.pixelSize: 24
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            minimumPointSize: 24
            minimumPixelSize: 24
            font.family: semiboldPoppins.name
            anchors.rightMargin: 0
            anchors.leftMargin: 0
            anchors.topMargin: 63
            onTextChanged: connectionSuccessTextAnimator.restart()
            opacity: 0
            OpacityAnimator {
                        id: connectionSuccessTextAnimator
                        target: connectionSuccessText
                        from: 0.1
                        to:1.0
                        duration:2000
                        running:true
                    }
        }
        Text {
            id: onlineUpdateSuccessText
            color: "#d1b5d1"
            text: backend.onlineUpdateSuccessText
            // text: qsTr("Online Updation Success")
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: connectionSuccessText.bottom
            font.pixelSize: 24
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            minimumPointSize: 24
            minimumPixelSize: 24
            font.family: semiboldPoppins.name
            anchors.rightMargin: 0
            anchors.leftMargin: 0
            anchors.topMargin: 25
            onTextChanged: onlineUpdateSuccessTextAnimator.restart()
            opacity: 0
            OpacityAnimator {
                        id: onlineUpdateSuccessTextAnimator
                        target: onlineUpdateSuccessText
                        from: 0.1
                        to:1.0
                        duration:2000
                        running:true
                    }
        }
        Text {
            id: taskFinishedText
            color: "#d1b5d1"
            text: backend.taskFinishedText
            // text: qsTr("Task Finished")
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: onlineUpdateSuccessText.bottom
            font.pixelSize: 24
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            minimumPointSize: 24
            minimumPixelSize: 24
            font.family: semiboldPoppins.name
            anchors.rightMargin: 0
            anchors.leftMargin: 0
            anchors.topMargin: 25
            onTextChanged: taskFinishedTextAnimator.restart()
            opacity: 0
            OpacityAnimator {
                        id: taskFinishedTextAnimator
                        target: taskFinishedText
                        from: 0.1
                        to:1.0
                        duration:2000
                        running:true
                    }
        }

    }

    Text {
        id: copyrightText
        height: 22
        text: qsTr("© Neo productions 2023")
        anchors.bottom: parent.bottom
        font.pixelSize: 12
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottomMargin: 8
        anchors.verticalCenterOffset: 276
        font.family: regularPoppins.name
        color: "#7DE2E2E2"
      }
    //    Connections {
//    target: updatePriceListButton
//    function onClicked() {
//        taskFinishedText.text = "YAY"
//        loadingMaskRectangle.visible = 'false'
//        mainBusyIndicator.running = false
//        console.log("HELLO")
//    }
//    }


}


